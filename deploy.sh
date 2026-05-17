#!/bin/bash
# DiamondCode deploy — pushes backend to Railway + frontend to Vercel
# Usage: ./deploy.sh

set -e
VERCEL=/opt/homebrew/bin/vercel

# Primary (new, simpler) link + the old one kept live as a fallback so
# existing bookmarks never break. Both get refreshed every deploy.
PRIMARY_ALIAS="diamond-code-seven.vercel.app"
LEGACY_ALIAS="frontend-nine-alpha-51.vercel.app"

echo "▶ Pushing backend to Railway..."
git push origin main

echo ""
echo "▶ Deploying frontend to Vercel..."
cd "$(dirname "$0")/frontend"
DEPLOY_URL=$($VERCEL --prod --yes 2>&1 | grep "^Production:" | tail -1 | awk '{print $2}')
echo "  Deployed: $DEPLOY_URL"

echo ""
echo "▶ Updating aliases"
$VERCEL alias set "$DEPLOY_URL" "$PRIMARY_ALIAS"
$VERCEL alias set "$DEPLOY_URL" "$LEGACY_ALIAS"

echo ""
echo "✓ Live at https://$PRIMARY_ALIAS"
echo "  (legacy: https://$LEGACY_ALIAS still works)"
