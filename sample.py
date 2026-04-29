git config --global user.name "SaiSrikar-Ravipati_cvsh"
git config --global user.email "SaiSrikar.Ravipati@CVSHealth.com"

ls -al ~/.ssh


ssh-keygen -t ed25519 -C "SaiSrikar.Ravipati@CVSHealth.com" -f ~/.ssh/id_ed25519_cvs


eval "$(ssh-agent -s)"
ssh-add --apple-use-keychain ~/.ssh/id_ed25519_cvs

---
ssh-add ~/.ssh/id_ed25519_cvs

cat >> ~/.ssh/config <<'EOF'

Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_cvs
  AddKeysToAgent yes
  UseKeychain yes
EOF

chmod 600 ~/.ssh/config


pbcopy < ~/.ssh/id_ed25519_cvs.pub


ssh -T git@github.com


cd ~/april
git clone -b sai-test git@github.com:cvs-health-source-code/pfme.git


---------------------------------------


