# Deployment Instructions for GitHub Pages

## Repository Setup

1. **Create a new repository on GitHub:**
   - Go to https://github.com/new
   - Repository name: `tagparkingboh.github.io`
   - Make it Public
   - DO NOT initialize with README, .gitignore, or license
   - Click "Create repository"

2. **Push your code:**

```bash
cd /Users/markcustard/Downloads/Tag/tag-website

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Airport meet & greet service website"

# Add remote repository
git remote add origin https://github.com/tagparkingboh/tagparkingboh.github.io.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

3. **Enable GitHub Pages:**
   - Go to your repository on GitHub
   - Click "Settings" tab
   - Click "Pages" in the left sidebar
   - Under "Build and deployment":
     - Source: Select "GitHub Actions"
   - Save

4. **Wait for deployment:**
   - Go to the "Actions" tab in your repository
   - Watch the deployment workflow run
   - Once complete (green checkmark), your site will be live at:
     **https://tagparkingboh.github.io**

## Local Development

To run locally:
```bash
npm run dev
```

To build for production:
```bash
npm run build
```

To preview production build:
```bash
npm run preview
```

## Updating the Site

After making changes:
```bash
git add .
git commit -m "Description of changes"
git push
```

The site will automatically rebuild and deploy via GitHub Actions.
