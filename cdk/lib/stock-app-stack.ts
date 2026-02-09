import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as targets from 'aws-cdk-lib/aws-elasticloadbalancingv2-targets';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as iam from 'aws-cdk-lib/aws-iam';
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
    userData.addCommands(
      'yum update -y',
      'yum install -y python3.11 python3.11-pip unzip',
      'cd /home/ec2-user',
      `aws s3 cp s3://${deployBucket}/stock-app.zip .`,
      'unzip -q stock-app.zip',
      'python3.11 -m venv venv',
      // Run in same shell to preserve venv activation
      'cd /home/ec2-user && source venv/bin/activate && pip install -r requirements.txt',
      'cd /home/ec2-user && source venv/bin/activate && nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > /var/log/streamlit.log 2>&1 &',
      // Wait for Streamlit to start
      'sleep 10'
    );

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
