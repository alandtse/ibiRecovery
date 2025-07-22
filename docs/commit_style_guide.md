# Commit Style Guide

## Commit Message Format

```
<type>: <description>

[optional body]

[optional footer]
```

## Rules

### Title Line (First Line)

- **Maximum 50 characters** (hard limit)
- **Start with lowercase** after the type
- **No period** at the end
- **Imperative mood** ("add" not "added" or "adds")

### Body (Optional)

- **Wrap at 72 characters** per line
- **Blank line** between title and body
- **Explain what and why**, not how

### Types

- `feat`: New feature
- `fix`: Bug fix
- `perf`: Performance improvement
- `docs`: Documentation changes
- `test`: Test additions/modifications
- `refactor`: Code refactoring
- `style`: Code style/formatting
- `chore`: Maintenance tasks

## Examples

### Good Commit Titles

```
feat: add directory conflict resolution
fix: prevent rsync rate limiting in resume mode
perf: optimize database queries for large datasets
docs: update installation requirements
```

### Bad Commit Titles (Too Long)

```
❌ feat: intelligent directory conflict resolution and enhanced rsync progress (75 chars)
❌ fix: eliminate confusing "Source file not found" warnings by filtering directory metadata (89 chars)
❌ fix: replace ALL remaining mkdir calls with safe_mkdir across entire codebase (77 chars)
```

### Better Versions

```
✅ feat: add directory conflict resolution (39 chars)
✅ fix: filter directory metadata preventing warnings (50 chars)
✅ fix: replace mkdir calls with safe_mkdir (37 chars)
```

## Pre-Commit Hook

To enforce these rules, use:

```bash
git config --global commit.template .gitmessage
```

Where `.gitmessage` contains:

```
# Title: 50 chars max ################# -> |
#
# Body: Wrap at 72 chars ##################################### -> |
#
# Types: feat, fix, perf, docs, test, refactor, style, chore
#
# Remember:
# - Use imperative mood in title
# - Explain what and why, not how
# - Reference issues: "Closes #123"
```
