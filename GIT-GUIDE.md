# Git Guide - Toy Seller Site

## ✅ Git Setup Complete

Your repository has been initialized with an initial commit containing all project files.

**Current branch**: `main`
**Initial commit**: `5b9964d` - "Initial commit: Toy Seller Site with SEO features"

---

## 📁 What's Being Tracked

Git is tracking:
- ✅ All source code (app.py, templates, static files)
- ✅ Documentation (README.md, SEO-FEATURES.md)
- ✅ Configuration files (.gitignore, requirements.txt)
- ✅ Sample content (products and blog posts)

Git is **NOT** tracking (via .gitignore):
- ❌ `venv/` - Virtual environment
- ❌ `.env` - Environment secrets
- ❌ `data/` - User accounts and data
- ❌ `static/images/*` - Uploaded product images
- ❌ `__pycache__/` - Python cache files

---

## 🔄 Common Git Workflows

### Making Changes

```bash
# 1. Edit files via admin dashboard or code editor
# 2. Check what changed
git status

# 3. See detailed changes
git diff

# 4. Stage changes
git add .

# 5. Commit with message
git commit -m "Add new product categories"

# Or stage and commit together
git commit -am "Update product prices"
```

### Viewing History

```bash
# See commit history
git log

# See compact history
git log --oneline

# See last 5 commits
git log -5

# See changes in a commit
git show 5b9964d
```

### Undoing Changes

```bash
# Discard uncommitted changes to a file
git checkout -- app.py

# Discard all uncommitted changes
git reset --hard

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1
```

---

## 🌐 Setting Up Remote Repository

### Option 1: GitHub

```bash
# Create repo on GitHub, then:
git remote add origin https://github.com/yourusername/toy-seller-site.git
git branch -M main
git push -u origin main

# Future pushes:
git push
```

### Option 2: GitLab

```bash
# Create project on GitLab, then:
git remote add origin https://gitlab.com/yourusername/toy-seller-site.git
git push -u origin main
```

### Option 3: Bitbucket

```bash
# Create repository on Bitbucket, then:
git remote add origin https://bitbucket.org/yourusername/toy-seller-site.git
git push -u origin main
```

---

## 🔀 Branching Strategy

### Feature Development

```bash
# Create and switch to feature branch
git checkout -b feature/new-category-system

# Make changes and commit
git add .
git commit -m "Implement subcategory support"

# Switch back to main
git checkout main

# Merge feature
git merge feature/new-category-system

# Delete feature branch
git branch -d feature/new-category-system
```

### Quick Fixes

```bash
# Create hotfix branch
git checkout -b hotfix/fix-price-display

# Fix and commit
git commit -am "Fix price decimal formatting"

# Merge to main
git checkout main
git merge hotfix/fix-price-display
```

---

## 📦 Daily Workflow Example

### End of Day Commit

```bash
# See what changed today
git status
git diff

# Commit your changes
git add .
git commit -m "Daily update: Added 5 new products, updated pricing"

# If using remote repo
git push
```

### Starting Next Day

```bash
# If using remote repo, pull latest
git pull

# Create feature branch for today's work
git checkout -b feature/holiday-products
```

---

## 🎯 Recommended Commit Messages

**Good commit messages**:
- `Add new product: Blue Robot Toy`
- `Update SEO meta tags for product pages`
- `Fix image upload bug in admin dashboard`
- `Improve mobile responsive design for products page`
- `Add Black Friday sale banner to homepage`

**Bad commit messages**:
- `changes`
- `fix`
- `update`
- `wip`

**Format**:
```
[Type]: Brief description

Optional detailed explanation of what and why.

- Bullet points for multiple changes
- Another change
```

**Types**: Add, Update, Fix, Remove, Refactor, Improve

---

## 🔒 Managing Secrets

Your `.env` file is **ignored by git** (not tracked). This is important!

**Never commit**:
- `.env` (contains SECRET_KEY)
- `data/users.json` (contains password hashes)
- Any API keys or credentials

**Safe to commit**:
- `.env.example` (template without real secrets)
- Code that reads from `.env`

---

## 🚀 Deployment Workflow

### With Git Remote

```bash
# On your production server
git clone https://github.com/yourusername/toy-seller-site.git
cd toy-seller-site

# Setup
cp .env.example .env
# Edit .env with production secrets
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
python3 app.py
```

### Updating Production

```bash
# On production server
git pull
pip install -r requirements.txt  # If requirements changed
sudo systemctl restart toy-seller  # Restart service
```

---

## 📊 Checking Repository Size

```bash
# See repository size
du -sh .git

# See largest files
git ls-files | xargs ls -lh | sort -k5 -hr | head -20
```

---

## 🔧 Git Configuration

### Set Your Identity

```bash
git config user.name "Your Name"
git config user.email "your.email@example.com"

# For this project only (already configured)
# Or globally:
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Useful Aliases

```bash
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.cm commit
git config --global alias.lg "log --oneline --graph --decorate"

# Now you can use: git st, git co, git br, etc.
```

---

## 🆘 Common Issues

### Accidentally Committed .env

```bash
# Remove from git but keep file
git rm --cached .env
git commit -m "Remove .env from tracking"

# Make sure .gitignore contains .env
```

### Want to Ignore New Files After Committing

```bash
# Add to .gitignore
echo "newfile.txt" >> .gitignore

# Remove from git
git rm --cached newfile.txt
git commit -m "Stop tracking newfile.txt"
```

### Committed to Wrong Branch

```bash
# If you haven't pushed yet
git reset --soft HEAD~1  # Undo commit, keep changes
git stash  # Save changes
git checkout correct-branch
git stash pop  # Apply changes
git commit -m "Your commit message"
```

---

## 📚 Quick Reference

```bash
# Status
git status                    # See changes
git diff                      # See detailed changes
git log                       # See history

# Basic workflow
git add .                     # Stage all changes
git commit -m "message"       # Commit
git push                      # Push to remote

# Branches
git branch                    # List branches
git checkout -b new-branch    # Create and switch
git merge other-branch        # Merge

# Remote
git remote -v                 # List remotes
git pull                      # Fetch and merge
git push                      # Push commits

# Undo
git checkout -- file          # Discard changes
git reset --hard              # Discard all changes
git revert <commit>           # Undo a commit (safe)
```

---

## 🎓 Next Steps

1. **Set up remote repository** (GitHub/GitLab/Bitbucket)
2. **Create `.env`** from `.env.example` and add real secrets
3. **Commit regularly** - daily or after each significant change
4. **Use branches** for new features
5. **Write good commit messages** - your future self will thank you

---

**Resources**:
- Git Docs: https://git-scm.com/doc
- GitHub Guides: https://guides.github.com/
- Git Cheat Sheet: https://education.github.com/git-cheat-sheet-education.pdf
