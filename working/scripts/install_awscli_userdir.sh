#!/usr/bin/env bash
# Install AWS CLI v2 into the user's home. Runs ON the box. NO-SUDO FALLBACK ONLY.
#
# Adopted from Leela's aws_run/box/install_awscli.sh — that version has actually executed on a
# benchmark box (her RUN_LOG_20260814 §6), which is why it is copied rather than rewritten.
#
# On our box `ssm-user` has passwordless sudo, so the one-liner is the primary route:
#     sudo apt-get install -y awscli
# Use this script only if sudo turns out to be unavailable or apt has no candidate.
#
# WHY IT LOOKS LIKE THIS: Canonical's Ubuntu AMIs do not ship the AWS CLI (Amazon Linux does),
# and the box has no `unzip`. python3's zipfile substitutes — but extractall() drops the
# executable bit, hence the chmod, which is the step that bit Leela.
set -euo pipefail
ZIP=/tmp/awscliv2.zip
command -v aws >/dev/null 2>&1 && { echo "already installed: $(aws --version)"; exit 0; }
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "$ZIP"
python3 -c "import zipfile;zipfile.ZipFile('$ZIP').extractall('/tmp/awscli')"
chmod -R u+x /tmp/awscli/aws
/tmp/awscli/aws/install -i "$HOME/.local/aws-cli" -b "$HOME/.local/bin"
for rc in "$HOME/.bashrc" "$HOME/.profile"; do
  grep -q 'local/bin' "$rc" 2>/dev/null || echo 'export PATH=$HOME/.local/bin:$PATH' >> "$rc"
done
export PATH="$HOME/.local/bin:$PATH"
aws --version
# The box authenticates with its INSTANCE ROLE. If this prints a profile error, something set
# AWS_PROFILE — unset it.
aws sts get-caller-identity --output json
