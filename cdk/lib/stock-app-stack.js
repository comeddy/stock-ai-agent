"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.StockAppStack = void 0;
const cdk = require("aws-cdk-lib");
const ec2 = require("aws-cdk-lib/aws-ec2");
const ecs = require("aws-cdk-lib/aws-ecs");
const ecr = require("aws-cdk-lib/aws-ecr");
const elbv2 = require("aws-cdk-lib/aws-elasticloadbalancingv2");
const cloudfront = require("aws-cdk-lib/aws-cloudfront");
const origins = require("aws-cdk-lib/aws-cloudfront-origins");
const iam = require("aws-cdk-lib/aws-iam");
const logs = require("aws-cdk-lib/aws-logs");
const secretsmanager = require("aws-cdk-lib/aws-secretsmanager");
const s3 = require("aws-cdk-lib/aws-s3");
class StockAppStack extends cdk.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        // VPC
        const vpc = new ec2.Vpc(this, 'StockAppVpc', {
            maxAzs: 2,
            natGateways: 1,
        });
        // ==========================================================================
        // 로깅: ALB 및 CloudFront 액세스 로그용 S3 버킷
        // ==========================================================================
        const logBucket = new s3.Bucket(this, 'AccessLogBucket', {
            bucketName: `stock-app-logs-${cdk.Aws.ACCOUNT_ID}`,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
            autoDeleteObjects: true,
            // ALB 로그를 위한 ACL 설정
            objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
            // 90일 후 로그 자동 삭제
            lifecycleRules: [
                {
                    id: 'DeleteOldLogs',
                    expiration: cdk.Duration.days(90),
                    enabled: true,
                },
            ],
            // 암호화 설정
            encryption: s3.BucketEncryption.S3_MANAGED,
            // 퍼블릭 액세스 차단
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
        });
        // ==========================================================================
        // 보안: CloudFront Origin 검증용 비밀 헤더 생성
        // ALB는 이 헤더가 있는 요청만 허용하여 직접 접근을 차단
        // ==========================================================================
        const originVerifySecret = new secretsmanager.Secret(this, 'OriginVerifySecret', {
            description: 'Secret header value for CloudFront to ALB origin verification',
            generateSecretString: {
                excludePunctuation: true,
                passwordLength: 32,
            },
        });
        // Security Group for ALB
        // CloudFront Managed Prefix List를 사용하여 CloudFront IP만 허용
        const albSg = new ec2.SecurityGroup(this, 'AlbSecurityGroup', {
            vpc,
            description: 'Security group for ALB - CloudFront only',
            allowAllOutbound: true,
        });
        // CloudFront Managed Prefix List를 통해 CloudFront IP 범위만 허용
        // 이렇게 하면 ALB에 직접 접근이 불가능해짐
        const cloudfrontPrefixList = ec2.Peer.prefixList('pl-3b927c52'); // us-east-1 CloudFront prefix list
        albSg.addIngressRule(cloudfrontPrefixList, ec2.Port.tcp(80), 'Allow HTTP from CloudFront only');
        // ==========================================================================
        // ECR Repository
        // ==========================================================================
        const ecrRepository = new ecr.Repository(this, 'StockAppRepo', {
            repositoryName: 'stock-app',
            removalPolicy: cdk.RemovalPolicy.DESTROY,
            emptyOnDelete: true,
            lifecycleRules: [
                {
                    maxImageCount: 5,
                    description: 'Keep only 5 most recent images',
                },
            ],
        });
        // ==========================================================================
        // ECS Cluster
        // ==========================================================================
        const cluster = new ecs.Cluster(this, 'StockAppCluster', {
            vpc,
            clusterName: 'stock-app-cluster',
            containerInsightsV2: ecs.ContainerInsights.ENABLED,
        });
        // ==========================================================================
        // CloudWatch Log Group for ECS
        // ==========================================================================
        const logGroup = new logs.LogGroup(this, 'StockAppLogGroup', {
            logGroupName: '/ecs/stock-app',
            retention: logs.RetentionDays.ONE_MONTH,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        });
        // ==========================================================================
        // IAM Roles
        // ==========================================================================
        // Task Execution Role: ECR pull + CloudWatch logs
        const taskExecutionRole = new iam.Role(this, 'TaskExecutionRole', {
            assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'),
            ],
        });
        // Task Role: application-level permissions (Bedrock)
        const taskRole = new iam.Role(this, 'TaskRole', {
            assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonBedrockFullAccess'),
            ],
        });
        // ECS Exec requires SSM permissions on the task role
        taskRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'));
        // ==========================================================================
        // Security Group for Fargate
        // ==========================================================================
        const fargateSg = new ec2.SecurityGroup(this, 'FargateSecurityGroup', {
            vpc,
            description: 'Security group for Fargate tasks',
            allowAllOutbound: true,
        });
        fargateSg.addIngressRule(albSg, ec2.Port.tcp(8501), 'Allow Streamlit from ALB');
        // ==========================================================================
        // Fargate Task Definition
        // ==========================================================================
        const taskDefinition = new ecs.FargateTaskDefinition(this, 'StockAppTaskDef', {
            memoryLimitMiB: 4096,
            cpu: 2048,
            executionRole: taskExecutionRole,
            taskRole,
        });
        taskDefinition.addContainer('stock-app', {
            image: ecs.ContainerImage.fromEcrRepository(ecrRepository, 'latest'),
            portMappings: [{ containerPort: 8501 }],
            logging: ecs.LogDrivers.awsLogs({
                streamPrefix: 'stock-app',
                logGroup,
            }),
            healthCheck: {
                command: ['CMD-SHELL', 'python -c "import urllib.request; urllib.request.urlopen(\'http://localhost:8501/_stcore/health\')" || exit 1'],
                interval: cdk.Duration.seconds(30),
                timeout: cdk.Duration.seconds(5),
                startPeriod: cdk.Duration.seconds(60),
                retries: 3,
            },
        });
        // ==========================================================================
        // Fargate Service
        // ==========================================================================
        const fargateService = new ecs.FargateService(this, 'StockAppService', {
            cluster,
            taskDefinition,
            desiredCount: 1,
            minHealthyPercent: 100,
            maxHealthyPercent: 200,
            securityGroups: [fargateSg],
            vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
            enableExecuteCommand: true,
            circuitBreaker: { rollback: true },
        });
        // ==========================================================================
        // Application Load Balancer
        // ==========================================================================
        const alb = new elbv2.ApplicationLoadBalancer(this, 'StockAppAlb', {
            vpc,
            internetFacing: true,
            securityGroup: albSg,
        });
        // ALB 액세스 로그 활성화
        alb.logAccessLogs(logBucket, 'alb-logs');
        // Target Group (IP type for Fargate awsvpc networking)
        const targetGroup = new elbv2.ApplicationTargetGroup(this, 'StockAppTargetGroup', {
            vpc,
            port: 8501,
            protocol: elbv2.ApplicationProtocol.HTTP,
            targetType: elbv2.TargetType.IP,
            healthCheck: {
                path: '/_stcore/health',
                interval: cdk.Duration.seconds(30),
                timeout: cdk.Duration.seconds(5),
                healthyThresholdCount: 2,
                unhealthyThresholdCount: 3,
            },
        });
        // Attach Fargate service to target group
        fargateService.attachToApplicationTargetGroup(targetGroup);
        // ==========================================================================
        // ALB Listener 설정
        // 커스텀 헤더 검증을 통해 CloudFront 외 접근 차단
        // ==========================================================================
        const listener = alb.addListener('HttpListener', {
            port: 80,
            defaultAction: elbv2.ListenerAction.fixedResponse(403, {
                contentType: 'text/plain',
                messageBody: 'Access Denied - Direct access not allowed',
            }),
        });
        // X-Origin-Verify 헤더가 있는 요청만 허용
        listener.addAction('AllowCloudFrontOnly', {
            priority: 1,
            conditions: [
                elbv2.ListenerCondition.httpHeader('X-Origin-Verify', [originVerifySecret.secretValue.unsafeUnwrap()]),
            ],
            action: elbv2.ListenerAction.forward([targetGroup]),
        });
        // ==========================================================================
        // CloudFront Distribution
        // 비밀 헤더를 추가하여 Origin(ALB)으로 요청 전달
        // ==========================================================================
        const distribution = new cloudfront.Distribution(this, 'StockAppDistribution', {
            defaultBehavior: {
                origin: new origins.LoadBalancerV2Origin(alb, {
                    protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                    // CloudFront → ALB 요청에 비밀 헤더 추가
                    customHeaders: {
                        'X-Origin-Verify': originVerifySecret.secretValue.unsafeUnwrap(),
                    },
                }),
                viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
                cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
                originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
            },
            // CloudFront 액세스 로그 활성화
            enableLogging: true,
            logBucket: logBucket,
            logFilePrefix: 'cloudfront-logs/',
            logIncludesCookies: true,
        });
        // ==========================================================================
        // Outputs
        // ==========================================================================
        new cdk.CfnOutput(this, 'CloudFrontUrl', {
            value: `https://${distribution.distributionDomainName}`,
            description: 'CloudFront URL',
        });
        new cdk.CfnOutput(this, 'AlbDnsName', {
            value: alb.loadBalancerDnsName,
            description: 'ALB DNS Name',
        });
        new cdk.CfnOutput(this, 'LogBucketName', {
            value: logBucket.bucketName,
            description: 'S3 Bucket for ALB and CloudFront access logs',
        });
        new cdk.CfnOutput(this, 'EcrRepositoryUri', {
            value: ecrRepository.repositoryUri,
            description: 'ECR Repository URI for docker push',
        });
        new cdk.CfnOutput(this, 'EcsClusterName', {
            value: cluster.clusterName,
            description: 'ECS Cluster Name',
        });
        new cdk.CfnOutput(this, 'EcsServiceName', {
            value: fargateService.serviceName,
            description: 'ECS Service Name',
        });
    }
}
exports.StockAppStack = StockAppStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoic3RvY2stYXBwLXN0YWNrLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsic3RvY2stYXBwLXN0YWNrLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiI7OztBQUFBLG1DQUFtQztBQUNuQywyQ0FBMkM7QUFDM0MsMkNBQTJDO0FBQzNDLDJDQUEyQztBQUMzQyxnRUFBZ0U7QUFDaEUseURBQXlEO0FBQ3pELDhEQUE4RDtBQUM5RCwyQ0FBMkM7QUFDM0MsNkNBQTZDO0FBQzdDLGlFQUFpRTtBQUNqRSx5Q0FBeUM7QUFHekMsTUFBYSxhQUFjLFNBQVEsR0FBRyxDQUFDLEtBQUs7SUFDMUMsWUFBWSxLQUFnQixFQUFFLEVBQVUsRUFBRSxLQUFzQjtRQUM5RCxLQUFLLENBQUMsS0FBSyxFQUFFLEVBQUUsRUFBRSxLQUFLLENBQUMsQ0FBQztRQUV4QixNQUFNO1FBQ04sTUFBTSxHQUFHLEdBQUcsSUFBSSxHQUFHLENBQUMsR0FBRyxDQUFDLElBQUksRUFBRSxhQUFhLEVBQUU7WUFDM0MsTUFBTSxFQUFFLENBQUM7WUFDVCxXQUFXLEVBQUUsQ0FBQztTQUNmLENBQUMsQ0FBQztRQUVILDZFQUE2RTtRQUM3RSxxQ0FBcUM7UUFDckMsNkVBQTZFO1FBQzdFLE1BQU0sU0FBUyxHQUFHLElBQUksRUFBRSxDQUFDLE1BQU0sQ0FBQyxJQUFJLEVBQUUsaUJBQWlCLEVBQUU7WUFDdkQsVUFBVSxFQUFFLGtCQUFrQixHQUFHLENBQUMsR0FBRyxDQUFDLFVBQVUsRUFBRTtZQUNsRCxhQUFhLEVBQUUsR0FBRyxDQUFDLGFBQWEsQ0FBQyxPQUFPO1lBQ3hDLGlCQUFpQixFQUFFLElBQUk7WUFDdkIsb0JBQW9CO1lBQ3BCLGVBQWUsRUFBRSxFQUFFLENBQUMsZUFBZSxDQUFDLHNCQUFzQjtZQUMxRCxpQkFBaUI7WUFDakIsY0FBYyxFQUFFO2dCQUNkO29CQUNFLEVBQUUsRUFBRSxlQUFlO29CQUNuQixVQUFVLEVBQUUsR0FBRyxDQUFDLFFBQVEsQ0FBQyxJQUFJLENBQUMsRUFB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QVcsRUFBRSxnQkFBZ0I7U0FDOUIsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxZQUFZLEVBQUU7WUFDcEMsS0FBSyxFQUFFLEdBQUcsQ0FBQyxtQkFBbUI7WUFDOUIsV0FBVyxFQUFFLGNBQWM7U0FDNUIsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxlQUFlLEVBQUU7WUFDdkMsS0FBSyxFQUFFLFNBQVMsQ0FBQyxVQUFVO1lBQzNCLFdBQVcsRUFBRSw4Q0FBOEM7U0FDNUQsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxrQkFBa0IsRUFBRTtZQUMxQyxLQUFLLEVBQUUsYUFBYSxDQUFDLGFBQWE7WUFDbEMsV0FBVyxFQUFFLG9DQUFvQztTQUNsRCxDQUFDLENBQUM7UUFFSCxJQUFJLEdBQUcsQ0FBQyxTQUFTLENBQUMsSUFBSSxFQUFFLGdCQUFnQixFQUFFO1lBQ3hDLEtBQUssRUFBRSxPQUFPLENBQUMsV0FBVztZQUMxQixXQUFXLEVBQUUsa0JBQWtCO1NBQ2hDLENBQUMsQ0FBQztRQUVILElBQUksR0FBRyxDQUFDLFNBQVMsQ0FBQyxJQUFJLEVBQUUsZ0JBQWdCLEVBQUU7WUFDeEMsS0FBSyxFQUFFLGNBQWMsQ0FBQyxXQUFXO1lBQ2pDLFdBQVcsRUFBRSxrQkFBa0I7U0FDaEMsQ0FBQyxDQUFDO0lBQ0wsQ0FBQztDQUNGO0FBcFJELHNDQW9SQyIsInNvdXJjZXNDb250ZW50IjpbImltcG9ydCAqIGFzIGNkayBmcm9tICdhd3MtY2RrLWxpYic7XG5pbXBvcnQgKiBhcyBlYzIgZnJvbSAnYXdzLWNkay1saWIvYXdzLWVjMic7XG5pbXBvcnQgKiBhcyBlY3MgZnJvbSAnYXdzLWNkay1saWIvYXdzLWVjcyc7XG5pbXBvcnQgKiBhcyBlY3IgZnJvbSAnYXdzLWNkay1saWIvYXdzLWVjcic7XG5pbXBvcnQgKiBhcyBlbGJ2MiBmcm9tICdhd3MtY2RrLWxpYi9hd3MtZWxhc3RpY2xvYWRiYWxhbmNpbmd2Mic7XG5pbXBvcnQgKiBhcyBjbG91ZGZyb250IGZyb20gJ2F3cy1jZGstbGliL2F3cy1jbG91ZGZyb250JztcbmltcG9ydCAqIGFzIG9yaWdpbnMgZnJvbSAnYXdzLWNkay1saWIvYXdzLWNsb3VkZnJvbnQtb3JpZ2lucyc7XG5pbXBvcnQgKiBhcyBpYW0gZnJvbSAnYXdzLWNkay1saWIvYXdzLWlhbSc7XG5pbXBvcnQgKiBhcyBsb2dzIGZyb20gJ2F3cy1jZGstbGliL2F3cy1sb2dzJztcbmltcG9ydCAqIGFzIHNlY3JldHNtYW5hZ2VyIGZyb20gJ2F3cy1jZGstbGliL2F3cy1zZWNyZXRzbWFuYWdlcic7XG5pbXBvcnQgKiBhcyBzMyBmcm9tICdhd3MtY2RrLWxpYi9hd3MtczMnO1xuaW1wb3J0IHsgQ29uc3RydWN0IH0gZnJvbSAnY29uc3RydWN0cyc7XG5cbmV4cG9ydCBjbGFzcyBTdG9ja0FwcFN0YWNrIGV4dGVuZHMgY2RrLlN0YWNrIHtcbiAgY29uc3RydWN0b3Ioc2NvcGU6IENvbnN0cnVjdCwgaWQ6IHN0cmluZywgcHJvcHM/OiBjZGsuU3RhY2tQcm9wcykge1xuICAgIHN1cGVyKHNjb3BlLCBpZCwgcHJvcHMpO1xuXG4gICAgLy8gVlBDXG4gICAgY29uc3QgdnBjID0gbmV3IGVjMi5WcGModGhpcywgJ1N0b2NrQXBwVnBjJywge1xuICAgICAgbWF4QXpzOiAyLFxuICAgICAgbmF0R2F0ZXdheXM6IDEsXG4gICAgfSk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIOuhnOq5hTogQUxCIOuwjyBDbG91ZEZyb250IOyVoeyEuOyKpCDroZzqt7jsmqkgUzMg67KE7YK3XG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICBjb25zdCBsb2dCdWNrZXQgPSBuZXcgczMuQnVja2V0KHRoaXMsICdBY2Nlc3NMb2dCdWNrZXQnLCB7XG4gICAgICBidWNrZXROYW1lOiBgc3RvY2stYXBwLWxvZ3MtJHtjZGsuQXdzLkFDQ09VTlRfSUR9YCxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LkRFU1RST1ksXG4gICAgICBhdXRvRGVsZXRlT2JqZWN0czogdHJ1ZSxcbiAgICAgIC8vIEFMQiDroZzqt7jrpbwg7JyE7ZWcIEFDTCDshKTsoJVcbiAgICAgIG9iamVjdE93bmVyc2hpcDogczMuT2JqZWN0T3duZXJzaGlwLkJVQ0tFVF9PV05FUl9QUkVGRVJSRUQsXG4gICAgICAvLyA5MOydvCDtm4Qg66Gc6re4IOyekOuPmSDsgq3soJxcbiAgICAgIGxpZmVjeWNsZVJ1bGVzOiBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogJ0RlbGV0ZU9sZExvZ3MnLFxuICAgICAgICAgIGV4cGlyYXRpb246IGNkay5EdXJhdGlvbi5kYXlzKDkwKSxcbiAgICAgICAgICBlbmFibGVkOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIC8vIOyVlO2YuO2ZlCDshKTsoJVcbiAgICAgIGVuY3J5cHRpb246IHMzLkJ1Y2tldEVuY3J5cHRpb24uUzNfTUFOQUdFRCxcbiAgICAgIC8vIO2NvOu4lOumrSDslaHshLjsiqQg7LCo64uoXG4gICAgICBibG9ja1B1YmxpY0FjY2VzczogczMuQmxvY2tQdWJsaWNBY2Nlc3MuQkxPQ0tfQUxMLFxuICAgIH0pO1xuXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICAvLyDrs7TslYg6IENsb3VkRnJvbnQgT3JpZ2luIOqygOymneyaqSDruYTrsIAg7Zek642UIOyDneyEsVxuICAgIC8vIEFMQuuKlCDsnbQg7Zek642U6rCAIOyeiOuKlCDsmpTssq3rp4wg7ZeI7Jqp7ZWY7JesIOyngeygkSDsoJHqt7zsnYQg7LCo64uoXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICBjb25zdCBvcmlnaW5WZXJpZnlTZWNyZXQgPSBuZXcgc2VjcmV0c21hbmFnZXIuU2VjcmV0KHRoaXMsICdPcmlnaW5WZXJpZnlTZWNyZXQnLCB7XG4gICAgICBkZXNjcmlwdGlvbjogJ1NlY3JldCBoZWFkZXIgdmFsdWUgZm9yIENsb3VkRnJvbnQgdG8gQUxCIG9yaWdpbiB2ZXJpZmljYXRpb24nLFxuICAgICAgZ2VuZXJhdGVTZWNyZXRTdHJpbmc6IHtcbiAgICAgICAgZXhjbHVkZVB1bmN0dWF0aW9uOiB0cnVlLFxuICAgICAgICBwYXNzd29yZExlbmd0aDogMzIsXG4gICAgICB9LFxuICAgIH0pO1xuXG4gICAgLy8gU2VjdXJpdHkgR3JvdXAgZm9yIEFMQlxuICAgIC8vIENsb3VkRnJvbnQgTWFuYWdlZCBQcmVmaXggTGlzdOulvCDsgqzsmqntlZjsl6wgQ2xvdWRGcm9udCBJUOunjCDtl4jsmqlcbiAgICBjb25zdCBhbGJTZyA9IG5ldyBlYzIuU2VjdXJpdHlHcm91cCh0aGlzLCAnQWxiU2VjdXJpdHlHcm91cCcsIHtcbiAgICAgIHZwYyxcbiAgICAgIGRlc2NyaXB0aW9uOiAnU2VjdXJpdHkgZ3JvdXAgZm9yIEFMQiAtIENsb3VkRnJvbnQgb25seScsXG4gICAgICBhbGxvd0FsbE91dGJvdW5kOiB0cnVlLFxuICAgIH0pO1xuXG4gICAgLy8gQ2xvdWRGcm9udCBNYW5hZ2VkIFByZWZpeCBMaXN066W8IO2Gte2VtCBDbG91ZEZyb250IElQIOuylOychOunjCDtl4jsmqlcbiAgICAvLyDsnbTroIfqsowg7ZWY66m0IEFMQuyXkCDsp4HsoJEg7KCR6re87J20IOu2iOqwgOuKpe2VtOynkFxuICAgIGNvbnN0IGNsb3VkZnJvbnRQcmVmaXhMaXN0ID0gZWMyLlBlZXIucHJlZml4TGlzdCgncGwtM2I5MjdjNTInKTsgLy8gdXMtZWFzdC0xIENsb3VkRnJvbnQgcHJlZml4IGxpc3RcbiAgICBhbGJTZy5hZGRJbmdyZXNzUnVsZShjbG91ZGZyb250UHJlZml4TGlzdCwgZWMyLlBvcnQudGNwKDgwKSwgJ0FsbG93IEhUVFAgZnJvbSBDbG91ZEZyb250IG9ubHknKTtcblxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgLy8gRUNSIFJlcG9zaXRvcnlcbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIGNvbnN0IGVjclJlcG9zaXRvcnkgPSBuZXcgZWNyLlJlcG9zaXRvcnkodGhpcywgJ1N0b2NrQXBwUmVwbycsIHtcbiAgICAgIHJlcG9zaXRvcnlOYW1lOiAnc3RvY2stYXBwJyxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LkRFU1RST1ksXG4gICAgICBlbXB0eU9uRGVsZXRlOiB0cnVlLFxuICAgICAgbGlmZWN5Y2xlUnVsZXM6IFtcbiAgICAgICAge1xuICAgICAgICAgIG1heEltYWdlQ291bnQ6IDUsXG4gICAgICAgICAgZGVzY3JpcHRpb246ICdLZWVwIG9ubHkgNSBtb3N0IHJlY2VudCBpbWFnZXMnLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICB9KTtcblxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgLy8gRUNTIENsdXN0ZXJcbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIGNvbnN0IGNsdXN0ZXIgPSBuZXcgZWNzLkNsdXN0ZXIodGhpcywgJ1N0b2NrQXBwQ2x1c3RlcicsIHtcbiAgICAgIHZwYyxcbiAgICAgIGNsdXN0ZXJOYW1lOiAnc3RvY2stYXBwLWNsdXN0ZXInLFxuICAgICAgY29udGFpbmVySW5zaWdodHNWMjogZWNzLkNvbnRhaW5lckluc2lnaHRzLkVOQUJMRUQsXG4gICAgfSk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIENsb3VkV2F0Y2ggTG9nIEdyb3VwIGZvciBFQ1NcbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIGNvbnN0IGxvZ0dyb3VwID0gbmV3IGxvZ3MuTG9nR3JvdXAodGhpcywgJ1N0b2NrQXBwTG9nR3JvdXAnLCB7XG4gICAgICBsb2dHcm91cE5hbWU6ICcvZWNzL3N0b2NrLWFwcCcsXG4gICAgICByZXRlbnRpb246IGxvZ3MuUmV0ZW50aW9uRGF5cy5PTkVfTU9OVEgsXG4gICAgICByZW1vdmFsUG9saWN5OiBjZGsuUmVtb3ZhbFBvbGljeS5ERVNUUk9ZLFxuICAgIH0pO1xuXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICAvLyBJQU0gUm9sZXNcbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuXG4gICAgLy8gVGFzayBFeGVjdXRpb24gUm9sZTogRUNSIHB1bGwgKyBDbG91ZFdhdGNoIGxvZ3NcbiAgICBjb25zdCB0YXNrRXhlY3V0aW9uUm9sZSA9IG5ldyBpYW0uUm9sZSh0aGlzLCAnVGFza0V4ZWN1dGlvblJvbGUnLCB7XG4gICAgICBhc3N1bWVkQnk6IG5ldyBpYW0uU2VydmljZVByaW5jaXBhbCgnZWNzLXRhc2tzLmFtYXpvbmF3cy5jb20nKSxcbiAgICAgIG1hbmFnZWRQb2xpY2llczogW1xuICAgICAgICBpYW0uTWFuYWdlZFBvbGljeS5mcm9tQXdzTWFuYWdlZFBvbGljeU5hbWUoJ3NlcnZpY2Utcm9sZS9BbWF6b25FQ1NUYXNrRXhlY3V0aW9uUm9sZVBvbGljeScpLFxuICAgICAgXSxcbiAgICB9KTtcblxuICAgIC8vIFRhc2sgUm9sZTogYXBwbGljYXRpb24tbGV2ZWwgcGVybWlzc2lvbnMgKEJlZHJvY2spXG4gICAgY29uc3QgdGFza1JvbGUgPSBuZXcgaWFtLlJvbGUodGhpcywgJ1Rhc2tSb2xlJywge1xuICAgICAgYXNzdW1lZEJ5OiBuZXcgaWFtLlNlcnZpY2VQcmluY2lwYWwoJ2Vjcy10YXNrcy5hbWF6b25hd3MuY29tJyksXG4gICAgICBtYW5hZ2VkUG9saWNpZXM6IFtcbiAgICAgICAgaWFtLk1hbmFnZWRQb2xpY3kuZnJvbUF3c01hbmFnZWRQb2xpY3lOYW1lKCdBbWF6b25CZWRyb2NrRnVsbEFjY2VzcycpLFxuICAgICAgXSxcbiAgICB9KTtcblxuICAgIC8vIEVDUyBFeGVjIHJlcXVpcmVzIFNTTSBwZXJtaXNzaW9ucyBvbiB0aGUgdGFzayByb2xlXG4gICAgdGFza1JvbGUuYWRkTWFuYWdlZFBvbGljeShcbiAgICAgIGlhbS5NYW5hZ2VkUG9saWN5LmZyb21Bd3NNYW5hZ2VkUG9saWN5TmFtZSgnQW1hem9uU1NNTWFuYWdlZEluc3RhbmNlQ29yZScpLFxuICAgICk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIFNlY3VyaXR5IEdyb3VwIGZvciBGYXJnYXRlXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICBjb25zdCBmYXJnYXRlU2cgPSBuZXcgZWMyLlNlY3VyaXR5R3JvdXAodGhpcywgJ0ZhcmdhdGVTZWN1cml0eUdyb3VwJywge1xuICAgICAgdnBjLFxuICAgICAgZGVzY3JpcHRpb246ICdTZWN1cml0eSBncm91cCBmb3IgRmFyZ2F0ZSB0YXNrcycsXG4gICAgICBhbGxvd0FsbE91dGJvdW5kOiB0cnVlLFxuICAgIH0pO1xuICAgIGZhcmdhdGVTZy5hZGRJbmdyZXNzUnVsZShhbGJTZywgZWMyLlBvcnQudGNwKDg1MDEpLCAnQWxsb3cgU3RyZWFtbGl0IGZyb20gQUxCJyk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIEZhcmdhdGUgVGFzayBEZWZpbml0aW9uXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICBjb25zdCB0YXNrRGVmaW5pdGlvbiA9IG5ldyBlY3MuRmFyZ2F0ZVRhc2tEZWZpbml0aW9uKHRoaXMsICdTdG9ja0FwcFRhc2tEZWYnLCB7XG4gICAgICBtZW1vcnlMaW1pdE1pQjogNDA5NixcbiAgICAgIGNwdTogMjA0OCxcbiAgICAgIGV4ZWN1dGlvblJvbGU6IHRhc2tFeGVjdXRpb25Sb2xlLFxuICAgICAgdGFza1JvbGUsXG4gICAgfSk7XG5cbiAgICB0YXNrRGVmaW5pdGlvbi5hZGRDb250YWluZXIoJ3N0b2NrLWFwcCcsIHtcbiAgICAgIGltYWdlOiBlY3MuQ29udGFpbmVySW1hZ2UuZnJvbUVjclJlcG9zaXRvcnkoZWNyUmVwb3NpdG9yeSwgJ2xhdGVzdCcpLFxuICAgICAgcG9ydE1hcHBpbmdzOiBbeyBjb250YWluZXJQb3J0OiA4NTAxIH1dLFxuICAgICAgbG9nZ2luZzogZWNzLkxvZ0RyaXZlcnMuYXdzTG9ncyh7XG4gICAgICAgIHN0cmVhbVByZWZpeDogJ3N0b2NrLWFwcCcsXG4gICAgICAgIGxvZ0dyb3VwLFxuICAgICAgfSksXG4gICAgICBoZWFsdGhDaGVjazoge1xuICAgICAgICBjb21tYW5kOiBbJ0NNRC1TSEVMTCcsICdweXRob24gLWMgXCJpbXBvcnQgdXJsbGliLnJlcXVlc3Q7IHVybGxpYi5yZXF1ZXN0LnVybG9wZW4oXFwnaHR0cDovL2xvY2FsaG9zdDo4NTAxL19zdGNvcmUvaGVhbHRoXFwnKVwiIHx8IGV4aXQgMSddLFxuICAgICAgICBpbnRlcnZhbDogY2RrLkR1cmF0aW9uLnNlY29uZHMoMzApLFxuICAgICAgICB0aW1lb3V0OiBjZGsuRHVyYXRpb24uc2Vjb25kcyg1KSxcbiAgICAgICAgc3RhcnRQZXJpb2Q6IGNkay5EdXJhdGlvbi5zZWNvbmRzKDYwKSxcbiAgICAgICAgcmV0cmllczogMyxcbiAgICAgIH0sXG4gICAgfSk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIEZhcmdhdGUgU2VydmljZVxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgY29uc3QgZmFyZ2F0ZVNlcnZpY2UgPSBuZXcgZWNzLkZhcmdhdGVTZXJ2aWNlKHRoaXMsICdTdG9ja0FwcFNlcnZpY2UnLCB7XG4gICAgICBjbHVzdGVyLFxuICAgICAgdGFza0RlZmluaXRpb24sXG4gICAgICBkZXNpcmVkQ291bnQ6IDEsXG4gICAgICBtaW5IZWFsdGh5UGVyY2VudDogMTAwLFxuICAgICAgbWF4SGVhbHRoeVBlcmNlbnQ6IDIwMCxcbiAgICAgIHNlY3VyaXR5R3JvdXBzOiBbZmFyZ2F0ZVNnXSxcbiAgICAgIHZwY1N1Ym5ldHM6IHsgc3VibmV0VHlwZTogZWMyLlN1Ym5ldFR5cGUuUFJJVkFURV9XSVRIX0VHUkVTUyB9LFxuICAgICAgZW5hYmxlRXhlY3V0ZUNvbW1hbmQ6IHRydWUsXG4gICAgICBjaXJjdWl0QnJlYWtlcjogeyByb2xsYmFjazogdHJ1ZSB9LFxuICAgIH0pO1xuXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICAvLyBBcHBsaWNhdGlvbiBMb2FkIEJhbGFuY2VyXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICBjb25zdCBhbGIgPSBuZXcgZWxidjIuQXBwbGljYXRpb25Mb2FkQmFsYW5jZXIodGhpcywgJ1N0b2NrQXBwQWxiJywge1xuICAgICAgdnBjLFxuICAgICAgaW50ZXJuZXRGYWNpbmc6IHRydWUsXG4gICAgICBzZWN1cml0eUdyb3VwOiBhbGJTZyxcbiAgICB9KTtcblxuICAgIC8vIEFMQiDslaHshLjsiqQg66Gc6re4IO2ZnOyEse2ZlFxuICAgIGFsYi5sb2dBY2Nlc3NMb2dzKGxvZ0J1Y2tldCwgJ2FsYi1sb2dzJyk7XG5cbiAgICAvLyBUYXJnZXQgR3JvdXAgKElQIHR5cGUgZm9yIEZhcmdhdGUgYXdzdnBjIG5ldHdvcmtpbmcpXG4gICAgY29uc3QgdGFyZ2V0R3JvdXAgPSBuZXcgZWxidjIuQXBwbGljYXRpb25UYXJnZXRHcm91cCh0aGlzLCAnU3RvY2tBcHBUYXJnZXRHcm91cCcsIHtcbiAgICAgIHZwYyxcbiAgICAgIHBvcnQ6IDg1MDEsXG4gICAgICBwcm90b2NvbDogZWxidjIuQXBwbGljYXRpb25Qcm90b2NvbC5IVFRQLFxuICAgICAgdGFyZ2V0VHlwZTogZWxidjIuVGFyZ2V0VHlwZS5JUCxcbiAgICAgIGhlYWx0aENoZWNrOiB7XG4gICAgICAgIHBhdGg6ICcvX3N0Y29yZS9oZWFsdGgnLFxuICAgICAgICBpbnRlcnZhbDogY2RrLkR1cmF0aW9uLnNlY29uZHMoMzApLFxuICAgICAgICB0aW1lb3V0OiBjZGsuRHVyYXRpb24uc2Vjb25kcyg1KSxcbiAgICAgICAgaGVhbHRoeVRocmVzaG9sZENvdW50OiAyLFxuICAgICAgICB1bmhlYWx0aHlUaHJlc2hvbGRDb3VudDogMyxcbiAgICAgIH0sXG4gICAgfSk7XG5cbiAgICAvLyBBdHRhY2ggRmFyZ2F0ZSBzZXJ2aWNlIHRvIHRhcmdldCBncm91cFxuICAgIGZhcmdhdGVTZXJ2aWNlLmF0dGFjaFRvQXBwbGljYXRpb25UYXJnZXRHcm91cCh0YXJnZXRHcm91cCk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIEFMQiBMaXN0ZW5lciDshKTsoJVcbiAgICAvLyDsu6TsiqTthYAg7Zek642UIOqygOymneydhCDthrXtlbQgQ2xvdWRGcm9udCDsmbgg7KCR6re8IOywqOuLqFxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgY29uc3QgbGlzdGVuZXIgPSBhbGIuYWRkTGlzdGVuZXIoJ0h0dHBMaXN0ZW5lcicsIHtcbiAgICAgIHBvcnQ6IDgwLFxuICAgICAgZGVmYXVsdEFjdGlvbjogZWxidjIuTGlzdGVuZXJBY3Rpb24uZml4ZWRSZXNwb25zZSg0MDMsIHtcbiAgICAgICAgY29udGVudFR5cGU6ICd0ZXh0L3BsYWluJyxcbiAgICAgICAgbWVzc2FnZUJvZHk6ICdBY2Nlc3MgRGVuaWVkIC0gRGlyZWN0IGFjY2VzcyBub3QgYWxsb3dlZCcsXG4gICAgICB9KSxcbiAgICB9KTtcblxuICAgIC8vIFgtT3JpZ2luLVZlcmlmeSDtl6TrjZTqsIAg7J6I64qUIOyalOyyreunjCDtl4jsmqlcbiAgICBsaXN0ZW5lci5hZGRBY3Rpb24oJ0FsbG93Q2xvdWRGcm9udE9ubHknLCB7XG4gICAgICBwcmlvcml0eTogMSxcbiAgICAgIGNvbmRpdGlvbnM6IFtcbiAgICAgICAgZWxidjIuTGlzdGVuZXJDb25kaXRpb24uaHR0cEhlYWRlcignWC1PcmlnaW4tVmVyaWZ5JywgW29yaWdpblZlcmlmeVNlY3JldC5zZWNyZXRWYWx1ZS51bnNhZmVVbndyYXAoKV0pLFxuICAgICAgXSxcbiAgICAgIGFjdGlvbjogZWxidjIuTGlzdGVuZXJBY3Rpb24uZm9yd2FyZChbdGFyZ2V0R3JvdXBdKSxcbiAgICB9KTtcblxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgLy8gQ2xvdWRGcm9udCBEaXN0cmlidXRpb25cbiAgICAvLyDruYTrsIAg7Zek642U66W8IOy2lOqwgO2VmOyXrCBPcmlnaW4oQUxCKeycvOuhnCDsmpTssq0g7KCE64usXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICBjb25zdCBkaXN0cmlidXRpb24gPSBuZXcgY2xvdWRmcm9udC5EaXN0cmlidXRpb24odGhpcywgJ1N0b2NrQXBwRGlzdHJpYnV0aW9uJywge1xuICAgICAgZGVmYXVsdEJlaGF2aW9yOiB7XG4gICAgICAgIG9yaWdpbjogbmV3IG9yaWdpbnMuTG9hZEJhbGFuY2VyVjJPcmlnaW4oYWxiLCB7XG4gICAgICAgICAgcHJvdG9jb2xQb2xpY3k6IGNsb3VkZnJvbnQuT3JpZ2luUHJvdG9jb2xQb2xpY3kuSFRUUF9PTkxZLFxuICAgICAgICAgIC8vIENsb3VkRnJvbnQg4oaSIEFMQiDsmpTssq3sl5Ag67mE67CAIO2XpOuNlCDstpTqsIBcbiAgICAgICAgICBjdXN0b21IZWFkZXJzOiB7XG4gICAgICAgICAgICAnWC1PcmlnaW4tVmVyaWZ5Jzogb3JpZ2luVmVyaWZ5U2VjcmV0LnNlY3JldFZhbHVlLnVuc2FmZVVud3JhcCgpLFxuICAgICAgICAgIH0sXG4gICAgICAgIH0pLFxuICAgICAgICB2aWV3ZXJQcm90b2NvbFBvbGljeTogY2xvdWRmcm9udC5WaWV3ZXJQcm90b2NvbFBvbGljeS5SRURJUkVDVF9UT19IVFRQUyxcbiAgICAgICAgYWxsb3dlZE1ldGhvZHM6IGNsb3VkZnJvbnQuQWxsb3dlZE1ldGhvZHMuQUxMT1dfQUxMLFxuICAgICAgICBjYWNoZVBvbGljeTogY2xvdWRmcm9udC5DYWNoZVBvbGljeS5DQUNISU5HX0RJU0FCTEVELFxuICAgICAgICBvcmlnaW5SZXF1ZXN0UG9saWN5OiBjbG91ZGZyb250Lk9yaWdpblJlcXVlc3RQb2xpY3kuQUxMX1ZJRVdFUixcbiAgICAgIH0sXG4gICAgICAvLyBDbG91ZEZyb250IOyVoeyEuOyKpCDroZzqt7gg7Zmc7ISx7ZmUXG4gICAgICBlbmFibGVMb2dnaW5nOiB0cnVlLFxuICAgICAgbG9nQnVja2V0OiBsb2dCdWNrZXQsXG4gICAgICBsb2dGaWxlUHJlZml4OiAnY2xvdWRmcm9udC1sb2dzLycsXG4gICAgICBsb2dJbmNsdWRlc0Nvb2tpZXM6IHRydWUsXG4gICAgfSk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIE91dHB1dHNcbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIG5ldyBjZGsuQ2ZuT3V0cHV0KHRoaXMsICdDbG91ZEZyb250VXJsJywge1xuICAgICAgdmFsdWU6IGBodHRwczovLyR7ZGlzdHJpYnV0aW9uLmRpc3RyaWJ1dGlvbkRvbWFpbk5hbWV9YCxcbiAgICAgIGRlc2NyaXB0aW9uOiAnQ2xvdWRGcm9udCBVUkwnLFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0FsYkRuc05hbWUnLCB7XG4gICAgICB2YWx1ZTogYWxiLmxvYWRCYWxhbmNlckRuc05hbWUsXG4gICAgICBkZXNjcmlwdGlvbjogJ0FMQiBETlMgTmFtZScsXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnTG9nQnVja2V0TmFtZScsIHtcbiAgICAgIHZhbHVlOiBsb2dCdWNrZXQuYnVja2V0TmFtZSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnUzMgQnVja2V0IGZvciBBTEIgYW5kIENsb3VkRnJvbnQgYWNjZXNzIGxvZ3MnLFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0VjclJlcG9zaXRvcnlVcmknLCB7XG4gICAgICB2YWx1ZTogZWNyUmVwb3NpdG9yeS5yZXBvc2l0b3J5VXJpLFxuICAgICAgZGVzY3JpcHRpb246ICdFQ1IgUmVwb3NpdG9yeSBVUkkgZm9yIGRvY2tlciBwdXNoJyxcbiAgICB9KTtcblxuICAgIG5ldyBjZGsuQ2ZuT3V0cHV0KHRoaXMsICdFY3NDbHVzdGVyTmFtZScsIHtcbiAgICAgIHZhbHVlOiBjbHVzdGVyLmNsdXN0ZXJOYW1lLFxuICAgICAgZGVzY3JpcHRpb246ICdFQ1MgQ2x1c3RlciBOYW1lJyxcbiAgICB9KTtcblxuICAgIG5ldyBjZGsuQ2ZuT3V0cHV0KHRoaXMsICdFY3NTZXJ2aWNlTmFtZScsIHtcbiAgICAgIHZhbHVlOiBmYXJnYXRlU2VydmljZS5zZXJ2aWNlTmFtZSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnRUNTIFNlcnZpY2UgTmFtZScsXG4gICAgfSk7XG4gIH1cbn1cbiJdfQ==