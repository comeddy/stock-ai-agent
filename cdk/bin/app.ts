#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { StockAppStack } from '../lib/stock-app-stack';

const app = new cdk.App();
new StockAppStack(app, 'StockAppStack', {
  env: { 
    account: process.env.CDK_DEFAULT_ACCOUNT, 
    region: 'us-east-1' 
  },
});
