import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export class StockAppStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
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
    taskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
    );

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
