#!/bin/bash
# DiamondCode deploy — pushes backend to Railway + frontend to Vercel
# Usage: ./deploy.sh

set -e
VERCEL=/opt/homebrew/bin/vercel
ALIAS="frontend-nine-alpha-51.vercel.app"

echo "▶ Pushing backend to Railway..."
git push origin main

echo ""
echo "▶ Deploying frontend to Vercel..."
cd "$(dirname "$0")/frontend"
DEPLOY_URL=$($VERCEL --prod --yes 2>&1 | grep "^Production:" | tail -1 | awk '{print $2}')
echo "  Deployed: $DEPLOY_URL"

echo ""
echo "▶ Updating alias → $ALIAS"
$VERCEL alias set "$DEPLOY_URL" "$ALIAS"

echo ""
echo "✓ Live at https://$ALIAS"
