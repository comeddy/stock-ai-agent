"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.StockAppStack = void 0;
const cdk = require("aws-cdk-lib");
const ec2 = require("aws-cdk-lib/aws-ec2");
const elbv2 = require("aws-cdk-lib/aws-elasticloadbalancingv2");
const targets = require("aws-cdk-lib/aws-elasticloadbalancingv2-targets");
const cloudfront = require("aws-cdk-lib/aws-cloudfront");
const origins = require("aws-cdk-lib/aws-cloudfront-origins");
const iam = require("aws-cdk-lib/aws-iam");
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
        // Security Group for EC2
        const ec2Sg = new ec2.SecurityGroup(this, 'Ec2SecurityGroup', {
            vpc,
            description: 'Security group for EC2',
            allowAllOutbound: true,
        });
        ec2Sg.addIngressRule(albSg, ec2.Port.tcp(8501), 'Allow Streamlit from ALB');
        // S3 bucket name (parameterized)
        const deployBucket = process.env.DEPLOY_BUCKET || 'stock-ai-agent-deploy-1770486416';
        // IAM Role for EC2
        const ec2Role = new iam.Role(this, 'Ec2Role', {
            assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
                iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonBedrockFullAccess'),
            ],
        });
        // S3 access for deployment
        ec2Role.addToPolicy(new iam.PolicyStatement({
            actions: ['s3:GetObject'],
            resources: [`arn:aws:s3:::${deployBucket}/*`],
        }));
        // User Data for EC2
        const userData = ec2.UserData.forLinux();
        userData.addCommands('yum update -y', 'yum install -y python3.11 python3.11-pip unzip', 'cd /home/ec2-user', `aws s3 cp s3://${deployBucket}/stock-app.zip .`, 'unzip -q stock-app.zip', 'python3.11 -m venv venv', 
        // Run in same shell to preserve venv activation
        'cd /home/ec2-user && source venv/bin/activate && pip install -r requirements.txt', 'cd /home/ec2-user && source venv/bin/activate && nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > /var/log/streamlit.log 2>&1 &', 
        // Wait for Streamlit to start
        'sleep 10');
        // EC2 Instance
        const instance = new ec2.Instance(this, 'StockAppInstance', {
            vpc,
            instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
            machineImage: ec2.MachineImage.latestAmazonLinux2023(),
            securityGroup: ec2Sg,
            role: ec2Role,
            userData,
            vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
        });
        // Application Load Balancer
        const alb = new elbv2.ApplicationLoadBalancer(this, 'StockAppAlb', {
            vpc,
            internetFacing: true,
            securityGroup: albSg,
        });
        // ==========================================================================
        // ALB 액세스 로그 활성화
        // ==========================================================================
        alb.logAccessLogs(logBucket, 'alb-logs');
        // Target Group
        const targetGroup = new elbv2.ApplicationTargetGroup(this, 'StockAppTargetGroup', {
            vpc,
            port: 8501,
            protocol: elbv2.ApplicationProtocol.HTTP,
            targets: [new targets.InstanceTarget(instance)],
            healthCheck: {
                path: '/',
                interval: cdk.Duration.seconds(30),
                timeout: cdk.Duration.seconds(5),
            },
        });
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
            // ==========================================================================
            // CloudFront 액세스 로그 활성화
            // ==========================================================================
            enableLogging: true,
            logBucket: logBucket,
            logFilePrefix: 'cloudfront-logs/',
            logIncludesCookies: true,
        });
        // Outputs
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
    }
}
exports.StockAppStack = StockAppStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoic3RvY2stYXBwLXN0YWNrLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsic3RvY2stYXBwLXN0YWNrLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiI7OztBQUFBLG1DQUFtQztBQUNuQywyQ0FBMkM7QUFDM0MsZ0VBQWdFO0FBQ2hFLDBFQUEwRTtBQUMxRSx5REFBeUQ7QUFDekQsOERBQThEO0FBQzlELDJDQUEyQztBQUMzQyxpRUFBaUU7QUFDakUseUNBQXlDO0FBR3pDLE1BQWEsYUFBYyxTQUFRLEdBQUcsQ0FBQyxLQUFLO0lBQzFDLFlBQVksS0FBZ0IsRUFBRSxFQUFVLEVBQUUsS0FBc0I7UUFDOUQsS0FBSyxDQUFDLEtBQUssRUFBRSxFQUFFLEVBQUUsS0FBSyxDQUFDLENBQUM7UUFFeEIsTUFBTTtRQUNOLE1BQU0sR0FBRyxHQUFHLElBQUksR0FBRyxDQUFDLEdBQUcsQ0FBQyxJQUFJLEVBQUUsYUFBYSxFQUFFO1lBQzNDLE1BQU0sRUFBRSxDQUFDO1lBQ1QsV0FBVyxFQUFFLENBQUM7U0FDZixDQUFDLENBQUM7UUFFSCw2RUFBNkU7UUFDN0UscUNBQXFDO1FBQ3JDLDZFQUE2RTtRQUM3RSxNQUFNLFNBQVMsR0FBRyxJQUFJLEVBQUUsQ0FBQyxNQUFNLENBQUMsSUFBSSxFQUFFLGlCQUFpQixFQUFFO1lBQ3ZELFVBQVUsRUFBRSxrQkFBa0IsR0FBRyxDQUFDLEdBQUcsQ0FBQyxVQUFVLEVBQUU7WUFDbEQsYUFBYSxFQUFFLEdBQUcsQ0FBQyxhQUFhLENBQUMsT0FBTztZQUN4QyxpQkFBaUIsRUFBRSxJQUFJO1lBQ3ZCLG9CQUFvQjtZQUNwQixlQUFlLEVBQUUsRUFBRSxDQUFDLGVBQWUsQ0FBQyxzQkFBc0I7WUFDMUQsaUJBQWlCO1lBQ2pCLGNBQWMsRUFBRTtnQkFDZDtvQkFDRSxFQUFFLEVBQUUsZUFBZTtvQkFDbkIsVUFBVSxFQUFFLEdBQUcsQ0FBQyxRQUFRLENBQUMsSUFBSSxDQUFDLEVBQUUsQ0FBQztvQkFDakMsT0FBTyxFQUFFLElB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QUUsVUFBVSxDQUFDLG9CQUFvQixDQUFDLGlCQUFpQjtnQkFDdkUsY0FBYyxFQUFFLFVBQVUsQ0FBQyxjQUFjLENBQUMsU0FBUztnQkFDbkQsV0FBVyxFQUFFLFVBQVUsQ0FBQyxXQUFXLENBQUMsZ0JBQWdCO2dCQUNwRCxtQkFBbUIsRUFBRSxVQUFVLENBQUMsbUJBQW1CLENBQUMsVUFBVTthQUMvRDtZQUNELDZFQUE2RTtZQUM3RSx3QkFBd0I7WUFDeEIsNkVBQTZFO1lBQzdFLGFBQWEsRUFBRSxJQUFJO1lBQ25CLFNBQVMsRUFBRSxTQUFTO1lBQ3BCLGFBQWEsRUFBRSxrQkFBa0I7WUFDakMsa0JBQWtCLEVBQUUsSUFBSTtTQUN6QixDQUFDLENBQUM7UUFFSCxVQUFVO1FBQ1YsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxlQUFlLEVBQUU7WUFDdkMsS0FBSyxFQUFFLFdBQVcsWUFBWSxDQUFDLHNCQUFzQixFQUFFO1lBQ3ZELFdBQVcsRUFBRSxnQkFBZ0I7U0FDOUIsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxZQUFZLEVBQUU7WUFDcEMsS0FBSyxFQUFFLEdBQUcsQ0FBQyxtQkFBbUI7WUFDOUIsV0FBVyxFQUFFLGNBQWM7U0FDNUIsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxlQUFlLEVBQUU7WUFDdkMsS0FBSyxFQUFFLFNBQVMsQ0FBQyxVQUFVO1lBQzNCLFdBQVcsRUFBRSw4Q0FBOEM7U0FDNUQsQ0FBQyxDQUFDO0lBQ0wsQ0FBQztDQUNGO0FBeE1ELHNDQXdNQyIsInNvdXJjZXNDb250ZW50IjpbImltcG9ydCAqIGFzIGNkayBmcm9tICdhd3MtY2RrLWxpYic7XG5pbXBvcnQgKiBhcyBlYzIgZnJvbSAnYXdzLWNkay1saWIvYXdzLWVjMic7XG5pbXBvcnQgKiBhcyBlbGJ2MiBmcm9tICdhd3MtY2RrLWxpYi9hd3MtZWxhc3RpY2xvYWRiYWxhbmNpbmd2Mic7XG5pbXBvcnQgKiBhcyB0YXJnZXRzIGZyb20gJ2F3cy1jZGstbGliL2F3cy1lbGFzdGljbG9hZGJhbGFuY2luZ3YyLXRhcmdldHMnO1xuaW1wb3J0ICogYXMgY2xvdWRmcm9udCBmcm9tICdhd3MtY2RrLWxpYi9hd3MtY2xvdWRmcm9udCc7XG5pbXBvcnQgKiBhcyBvcmlnaW5zIGZyb20gJ2F3cy1jZGstbGliL2F3cy1jbG91ZGZyb250LW9yaWdpbnMnO1xuaW1wb3J0ICogYXMgaWFtIGZyb20gJ2F3cy1jZGstbGliL2F3cy1pYW0nO1xuaW1wb3J0ICogYXMgc2VjcmV0c21hbmFnZXIgZnJvbSAnYXdzLWNkay1saWIvYXdzLXNlY3JldHNtYW5hZ2VyJztcbmltcG9ydCAqIGFzIHMzIGZyb20gJ2F3cy1jZGstbGliL2F3cy1zMyc7XG5pbXBvcnQgeyBDb25zdHJ1Y3QgfSBmcm9tICdjb25zdHJ1Y3RzJztcblxuZXhwb3J0IGNsYXNzIFN0b2NrQXBwU3RhY2sgZXh0ZW5kcyBjZGsuU3RhY2sge1xuICBjb25zdHJ1Y3RvcihzY29wZTogQ29uc3RydWN0LCBpZDogc3RyaW5nLCBwcm9wcz86IGNkay5TdGFja1Byb3BzKSB7XG4gICAgc3VwZXIoc2NvcGUsIGlkLCBwcm9wcyk7XG5cbiAgICAvLyBWUENcbiAgICBjb25zdCB2cGMgPSBuZXcgZWMyLlZwYyh0aGlzLCAnU3RvY2tBcHBWcGMnLCB7XG4gICAgICBtYXhBenM6IDIsXG4gICAgICBuYXRHYXRld2F5czogMSxcbiAgICB9KTtcblxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgLy8g66Gc6rmFOiBBTEIg67CPIENsb3VkRnJvbnQg7JWh7IS47IqkIOuhnOq3uOyaqSBTMyDrsoTtgrdcbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIGNvbnN0IGxvZ0J1Y2tldCA9IG5ldyBzMy5CdWNrZXQodGhpcywgJ0FjY2Vzc0xvZ0J1Y2tldCcsIHtcbiAgICAgIGJ1Y2tldE5hbWU6IGBzdG9jay1hcHAtbG9ncy0ke2Nkay5Bd3MuQUNDT1VOVF9JRH1gLFxuICAgICAgcmVtb3ZhbFBvbGljeTogY2RrLlJlbW92YWxQb2xpY3kuREVTVFJPWSxcbiAgICAgIGF1dG9EZWxldGVPYmplY3RzOiB0cnVlLFxuICAgICAgLy8gQUxCIOuhnOq3uOulvCDsnITtlZwgQUNMIOyEpOyglVxuICAgICAgb2JqZWN0T3duZXJzaGlwOiBzMy5PYmplY3RPd25lcnNoaXAuQlVDS0VUX09XTkVSX1BSRUZFUlJFRCxcbiAgICAgIC8vIDkw7J28IO2bhCDroZzqt7gg7J6Q64+ZIOyCreygnFxuICAgICAgbGlmZWN5Y2xlUnVsZXM6IFtcbiAgICAgICAge1xuICAgICAgICAgIGlkOiAnRGVsZXRlT2xkTG9ncycsXG4gICAgICAgICAgZXhwaXJhdGlvbjogY2RrLkR1cmF0aW9uLmRheXMoOTApLFxuICAgICAgICAgIGVuYWJsZWQ6IHRydWUsXG4gICAgICAgIH0sXG4gICAgICBdLFxuICAgICAgLy8g7JWU7Zi47ZmUIOyEpOyglVxuICAgICAgZW5jcnlwdGlvbjogczMuQnVja2V0RW5jcnlwdGlvbi5TM19NQU5BR0VELFxuICAgICAgLy8g7Y2867iU66atIOyVoeyEuOyKpCDssKjri6hcbiAgICAgIGJsb2NrUHVibGljQWNjZXNzOiBzMy5CbG9ja1B1YmxpY0FjY2Vzcy5CTE9DS19BTEwsXG4gICAgfSk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIOuztOyViDogQ2xvdWRGcm9udCBPcmlnaW4g6rKA7Kad7JqpIOu5hOuwgCDtl6TrjZQg7IOd7ISxXG4gICAgLy8gQUxC64qUIOydtCDtl6TrjZTqsIAg7J6I64qUIOyalOyyreunjCDtl4jsmqntlZjsl6wg7KeB7KCRIOygkeq3vOydhCDssKjri6hcbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIGNvbnN0IG9yaWdpblZlcmlmeVNlY3JldCA9IG5ldyBzZWNyZXRzbWFuYWdlci5TZWNyZXQodGhpcywgJ09yaWdpblZlcmlmeVNlY3JldCcsIHtcbiAgICAgIGRlc2NyaXB0aW9uOiAnU2VjcmV0IGhlYWRlciB2YWx1ZSBmb3IgQ2xvdWRGcm9udCB0byBBTEIgb3JpZ2luIHZlcmlmaWNhdGlvbicsXG4gICAgICBnZW5lcmF0ZVNlY3JldFN0cmluZzoge1xuICAgICAgICBleGNsdWRlUHVuY3R1YXRpb246IHRydWUsXG4gICAgICAgIHBhc3N3b3JkTGVuZ3RoOiAzMixcbiAgICAgIH0sXG4gICAgfSk7XG5cbiAgICAvLyBTZWN1cml0eSBHcm91cCBmb3IgQUxCXG4gICAgLy8gQ2xvdWRGcm9udCBNYW5hZ2VkIFByZWZpeCBMaXN066W8IOyCrOyaqe2VmOyXrCBDbG91ZEZyb250IElQ66eMIO2XiOyaqVxuICAgIGNvbnN0IGFsYlNnID0gbmV3IGVjMi5TZWN1cml0eUdyb3VwKHRoaXMsICdBbGJTZWN1cml0eUdyb3VwJywge1xuICAgICAgdnBjLFxuICAgICAgZGVzY3JpcHRpb246ICdTZWN1cml0eSBncm91cCBmb3IgQUxCIC0gQ2xvdWRGcm9udCBvbmx5JyxcbiAgICAgIGFsbG93QWxsT3V0Ym91bmQ6IHRydWUsXG4gICAgfSk7XG5cbiAgICAvLyBDbG91ZEZyb250IE1hbmFnZWQgUHJlZml4IExpc3Trpbwg7Ya17ZW0IENsb3VkRnJvbnQgSVAg67KU7JyE66eMIO2XiOyaqVxuICAgIC8vIOydtOugh+qyjCDtlZjrqbQgQUxC7JeQIOyngeygkSDsoJHqt7zsnbQg67aI6rCA64ql7ZW07KeQXG4gICAgY29uc3QgY2xvdWRmcm9udFByZWZpeExpc3QgPSBlYzIuUGVlci5wcmVmaXhMaXN0KCdwbC0zYjkyN2M1MicpOyAvLyB1cy1lYXN0LTEgQ2xvdWRGcm9udCBwcmVmaXggbGlzdFxuICAgIGFsYlNnLmFkZEluZ3Jlc3NSdWxlKGNsb3VkZnJvbnRQcmVmaXhMaXN0LCBlYzIuUG9ydC50Y3AoODApLCAnQWxsb3cgSFRUUCBmcm9tIENsb3VkRnJvbnQgb25seScpO1xuXG4gICAgLy8gU2VjdXJpdHkgR3JvdXAgZm9yIEVDMlxuICAgIGNvbnN0IGVjMlNnID0gbmV3IGVjMi5TZWN1cml0eUdyb3VwKHRoaXMsICdFYzJTZWN1cml0eUdyb3VwJywge1xuICAgICAgdnBjLFxuICAgICAgZGVzY3JpcHRpb246ICdTZWN1cml0eSBncm91cCBmb3IgRUMyJyxcbiAgICAgIGFsbG93QWxsT3V0Ym91bmQ6IHRydWUsXG4gICAgfSk7XG4gICAgZWMyU2cuYWRkSW5ncmVzc1J1bGUoYWxiU2csIGVjMi5Qb3J0LnRjcCg4NTAxKSwgJ0FsbG93IFN0cmVhbWxpdCBmcm9tIEFMQicpO1xuXG4gICAgLy8gUzMgYnVja2V0IG5hbWUgKHBhcmFtZXRlcml6ZWQpXG4gICAgY29uc3QgZGVwbG95QnVja2V0ID0gcHJvY2Vzcy5lbnYuREVQTE9ZX0JVQ0tFVCB8fCAnc3RvY2stYWktYWdlbnQtZGVwbG95LTE3NzA0ODY0MTYnO1xuXG4gICAgLy8gSUFNIFJvbGUgZm9yIEVDMlxuICAgIGNvbnN0IGVjMlJvbGUgPSBuZXcgaWFtLlJvbGUodGhpcywgJ0VjMlJvbGUnLCB7XG4gICAgICBhc3N1bWVkQnk6IG5ldyBpYW0uU2VydmljZVByaW5jaXBhbCgnZWMyLmFtYXpvbmF3cy5jb20nKSxcbiAgICAgIG1hbmFnZWRQb2xpY2llczogW1xuICAgICAgICBpYW0uTWFuYWdlZFBvbGljeS5mcm9tQXdzTWFuYWdlZFBvbGljeU5hbWUoJ0FtYXpvblNTTU1hbmFnZWRJbnN0YW5jZUNvcmUnKSxcbiAgICAgICAgaWFtLk1hbmFnZWRQb2xpY3kuZnJvbUF3c01hbmFnZWRQb2xpY3lOYW1lKCdBbWF6b25CZWRyb2NrRnVsbEFjY2VzcycpLFxuICAgICAgXSxcbiAgICB9KTtcblxuICAgIC8vIFMzIGFjY2VzcyBmb3IgZGVwbG95bWVudFxuICAgIGVjMlJvbGUuYWRkVG9Qb2xpY3kobmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgYWN0aW9uczogWydzMzpHZXRPYmplY3QnXSxcbiAgICAgIHJlc291cmNlczogW2Bhcm46YXdzOnMzOjo6JHtkZXBsb3lCdWNrZXR9LypgXSxcbiAgICB9KSk7XG5cbiAgICAvLyBVc2VyIERhdGEgZm9yIEVDMlxuICAgIGNvbnN0IHVzZXJEYXRhID0gZWMyLlVzZXJEYXRhLmZvckxpbnV4KCk7XG4gICAgdXNlckRhdGEuYWRkQ29tbWFuZHMoXG4gICAgICAneXVtIHVwZGF0ZSAteScsXG4gICAgICAneXVtIGluc3RhbGwgLXkgcHl0aG9uMy4xMSBweXRob24zLjExLXBpcCB1bnppcCcsXG4gICAgICAnY2QgL2hvbWUvZWMyLXVzZXInLFxuICAgICAgYGF3cyBzMyBjcCBzMzovLyR7ZGVwbG95QnVja2V0fS9zdG9jay1hcHAuemlwIC5gLFxuICAgICAgJ3VuemlwIC1xIHN0b2NrLWFwcC56aXAnLFxuICAgICAgJ3B5dGhvbjMuMTEgLW0gdmVudiB2ZW52JyxcbiAgICAgIC8vIFJ1biBpbiBzYW1lIHNoZWxsIHRvIHByZXNlcnZlIHZlbnYgYWN0aXZhdGlvblxuICAgICAgJ2NkIC9ob21lL2VjMi11c2VyICYmIHNvdXJjZSB2ZW52L2Jpbi9hY3RpdmF0ZSAmJiBwaXAgaW5zdGFsbCAtciByZXF1aXJlbWVudHMudHh0JyxcbiAgICAgICdjZCAvaG9tZS9lYzItdXNlciAmJiBzb3VyY2UgdmVudi9iaW4vYWN0aXZhdGUgJiYgbm9odXAgc3RyZWFtbGl0IHJ1biBhcHAucHkgLS1zZXJ2ZXIucG9ydCA4NTAxIC0tc2VydmVyLmFkZHJlc3MgMC4wLjAuMCA+IC92YXIvbG9nL3N0cmVhbWxpdC5sb2cgMj4mMSAmJyxcbiAgICAgIC8vIFdhaXQgZm9yIFN0cmVhbWxpdCB0byBzdGFydFxuICAgICAgJ3NsZWVwIDEwJ1xuICAgICk7XG5cbiAgICAvLyBFQzIgSW5zdGFuY2VcbiAgICBjb25zdCBpbnN0YW5jZSA9IG5ldyBlYzIuSW5zdGFuY2UodGhpcywgJ1N0b2NrQXBwSW5zdGFuY2UnLCB7XG4gICAgICB2cGMsXG4gICAgICBpbnN0YW5jZVR5cGU6IGVjMi5JbnN0YW5jZVR5cGUub2YoZWMyLkluc3RhbmNlQ2xhc3MuVDMsIGVjMi5JbnN0YW5jZVNpemUuTUVESVVNKSxcbiAgICAgIG1hY2hpbmVJbWFnZTogZWMyLk1hY2hpbmVJbWFnZS5sYXRlc3RBbWF6b25MaW51eDIwMjMoKSxcbiAgICAgIHNlY3VyaXR5R3JvdXA6IGVjMlNnLFxuICAgICAgcm9sZTogZWMyUm9sZSxcbiAgICAgIHVzZXJEYXRhLFxuICAgICAgdnBjU3VibmV0czogeyBzdWJuZXRUeXBlOiBlYzIuU3VibmV0VHlwZS5QUklWQVRFX1dJVEhfRUdSRVNTIH0sXG4gICAgfSk7XG5cbiAgICAvLyBBcHBsaWNhdGlvbiBMb2FkIEJhbGFuY2VyXG4gICAgY29uc3QgYWxiID0gbmV3IGVsYnYyLkFwcGxpY2F0aW9uTG9hZEJhbGFuY2VyKHRoaXMsICdTdG9ja0FwcEFsYicsIHtcbiAgICAgIHZwYyxcbiAgICAgIGludGVybmV0RmFjaW5nOiB0cnVlLFxuICAgICAgc2VjdXJpdHlHcm91cDogYWxiU2csXG4gICAgfSk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIEFMQiDslaHshLjsiqQg66Gc6re4IO2ZnOyEse2ZlFxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgYWxiLmxvZ0FjY2Vzc0xvZ3MobG9nQnVja2V0LCAnYWxiLWxvZ3MnKTtcblxuICAgIC8vIFRhcmdldCBHcm91cFxuICAgIGNvbnN0IHRhcmdldEdyb3VwID0gbmV3IGVsYnYyLkFwcGxpY2F0aW9uVGFyZ2V0R3JvdXAodGhpcywgJ1N0b2NrQXBwVGFyZ2V0R3JvdXAnLCB7XG4gICAgICB2cGMsXG4gICAgICBwb3J0OiA4NTAxLFxuICAgICAgcHJvdG9jb2w6IGVsYnYyLkFwcGxpY2F0aW9uUHJvdG9jb2wuSFRUUCxcbiAgICAgIHRhcmdldHM6IFtuZXcgdGFyZ2V0cy5JbnN0YW5jZVRhcmdldChpbnN0YW5jZSldLFxuICAgICAgaGVhbHRoQ2hlY2s6IHtcbiAgICAgICAgcGF0aDogJy8nLFxuICAgICAgICBpbnRlcnZhbDogY2RrLkR1cmF0aW9uLnNlY29uZHMoMzApLFxuICAgICAgICB0aW1lb3V0OiBjZGsuRHVyYXRpb24uc2Vjb25kcyg1KSxcbiAgICAgIH0sXG4gICAgfSk7XG5cbiAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgIC8vIEFMQiBMaXN0ZW5lciDshKTsoJVcbiAgICAvLyDsu6TsiqTthYAg7Zek642UIOqygOymneydhCDthrXtlbQgQ2xvdWRGcm9udCDsmbgg7KCR6re8IOywqOuLqFxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgY29uc3QgbGlzdGVuZXIgPSBhbGIuYWRkTGlzdGVuZXIoJ0h0dHBMaXN0ZW5lcicsIHtcbiAgICAgIHBvcnQ6IDgwLFxuICAgICAgZGVmYXVsdEFjdGlvbjogZWxidjIuTGlzdGVuZXJBY3Rpb24uZml4ZWRSZXNwb25zZSg0MDMsIHtcbiAgICAgICAgY29udGVudFR5cGU6ICd0ZXh0L3BsYWluJyxcbiAgICAgICAgbWVzc2FnZUJvZHk6ICdBY2Nlc3MgRGVuaWVkIC0gRGlyZWN0IGFjY2VzcyBub3QgYWxsb3dlZCcsXG4gICAgICB9KSxcbiAgICB9KTtcblxuICAgIC8vIFgtT3JpZ2luLVZlcmlmeSDtl6TrjZTqsIAg7J6I64qUIOyalOyyreunjCDtl4jsmqlcbiAgICBsaXN0ZW5lci5hZGRBY3Rpb24oJ0FsbG93Q2xvdWRGcm9udE9ubHknLCB7XG4gICAgICBwcmlvcml0eTogMSxcbiAgICAgIGNvbmRpdGlvbnM6IFtcbiAgICAgICAgZWxidjIuTGlzdGVuZXJDb25kaXRpb24uaHR0cEhlYWRlcignWC1PcmlnaW4tVmVyaWZ5JywgW29yaWdpblZlcmlmeVNlY3JldC5zZWNyZXRWYWx1ZS51bnNhZmVVbndyYXAoKV0pLFxuICAgICAgXSxcbiAgICAgIGFjdGlvbjogZWxidjIuTGlzdGVuZXJBY3Rpb24uZm9yd2FyZChbdGFyZ2V0R3JvdXBdKSxcbiAgICB9KTtcblxuICAgIC8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09XG4gICAgLy8gQ2xvdWRGcm9udCBEaXN0cmlidXRpb25cbiAgICAvLyDruYTrsIAg7Zek642U66W8IOy2lOqwgO2VmOyXrCBPcmlnaW4oQUxCKeycvOuhnCDsmpTssq0g7KCE64usXG4gICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICBjb25zdCBkaXN0cmlidXRpb24gPSBuZXcgY2xvdWRmcm9udC5EaXN0cmlidXRpb24odGhpcywgJ1N0b2NrQXBwRGlzdHJpYnV0aW9uJywge1xuICAgICAgZGVmYXVsdEJlaGF2aW9yOiB7XG4gICAgICAgIG9yaWdpbjogbmV3IG9yaWdpbnMuTG9hZEJhbGFuY2VyVjJPcmlnaW4oYWxiLCB7XG4gICAgICAgICAgcHJvdG9jb2xQb2xpY3k6IGNsb3VkZnJvbnQuT3JpZ2luUHJvdG9jb2xQb2xpY3kuSFRUUF9PTkxZLFxuICAgICAgICAgIC8vIENsb3VkRnJvbnQg4oaSIEFMQiDsmpTssq3sl5Ag67mE67CAIO2XpOuNlCDstpTqsIBcbiAgICAgICAgICBjdXN0b21IZWFkZXJzOiB7XG4gICAgICAgICAgICAnWC1PcmlnaW4tVmVyaWZ5Jzogb3JpZ2luVmVyaWZ5U2VjcmV0LnNlY3JldFZhbHVlLnVuc2FmZVVud3JhcCgpLFxuICAgICAgICAgIH0sXG4gICAgICAgIH0pLFxuICAgICAgICB2aWV3ZXJQcm90b2NvbFBvbGljeTogY2xvdWRmcm9udC5WaWV3ZXJQcm90b2NvbFBvbGljeS5SRURJUkVDVF9UT19IVFRQUyxcbiAgICAgICAgYWxsb3dlZE1ldGhvZHM6IGNsb3VkZnJvbnQuQWxsb3dlZE1ldGhvZHMuQUxMT1dfQUxMLFxuICAgICAgICBjYWNoZVBvbGljeTogY2xvdWRmcm9udC5DYWNoZVBvbGljeS5DQUNISU5HX0RJU0FCTEVELFxuICAgICAgICBvcmlnaW5SZXF1ZXN0UG9saWN5OiBjbG91ZGZyb250Lk9yaWdpblJlcXVlc3RQb2xpY3kuQUxMX1ZJRVdFUixcbiAgICAgIH0sXG4gICAgICAvLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PVxuICAgICAgLy8gQ2xvdWRGcm9udCDslaHshLjsiqQg66Gc6re4IO2ZnOyEse2ZlFxuICAgICAgLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT1cbiAgICAgIGVuYWJsZUxvZ2dpbmc6IHRydWUsXG4gICAgICBsb2dCdWNrZXQ6IGxvZ0J1Y2tldCxcbiAgICAgIGxvZ0ZpbGVQcmVmaXg6ICdjbG91ZGZyb250LWxvZ3MvJyxcbiAgICAgIGxvZ0luY2x1ZGVzQ29va2llczogdHJ1ZSxcbiAgICB9KTtcblxuICAgIC8vIE91dHB1dHNcbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCAnQ2xvdWRGcm9udFVybCcsIHtcbiAgICAgIHZhbHVlOiBgaHR0cHM6Ly8ke2Rpc3RyaWJ1dGlvbi5kaXN0cmlidXRpb25Eb21haW5OYW1lfWAsXG4gICAgICBkZXNjcmlwdGlvbjogJ0Nsb3VkRnJvbnQgVVJMJyxcbiAgICB9KTtcblxuICAgIG5ldyBjZGsuQ2ZuT3V0cHV0KHRoaXMsICdBbGJEbnNOYW1lJywge1xuICAgICAgdmFsdWU6IGFsYi5sb2FkQmFsYW5jZXJEbnNOYW1lLFxuICAgICAgZGVzY3JpcHRpb246ICdBTEIgRE5TIE5hbWUnLFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0xvZ0J1Y2tldE5hbWUnLCB7XG4gICAgICB2YWx1ZTogbG9nQnVja2V0LmJ1Y2tldE5hbWUsXG4gICAgICBkZXNjcmlwdGlvbjogJ1MzIEJ1Y2tldCBmb3IgQUxCIGFuZCBDbG91ZEZyb250IGFjY2VzcyBsb2dzJyxcbiAgICB9KTtcbiAgfVxufVxuIl19