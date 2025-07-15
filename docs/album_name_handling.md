# Album Name Handling in ibiRecovery

## Overview

ibiRecovery implements intelligent album name sanitization to ensure maximum compatibility with filesystem limitations while preserving as much of the original album name as possible.

## Sanitization Strategy

### Character Replacement (Not Removal)

Instead of simply removing problematic characters, ibiRecovery replaces them with safe alternatives:

| Problematic Character | Replacement | Reason                      |
| --------------------- | ----------- | --------------------------- | ------------------- |
| `/` (forward slash)   | `_`         | Directory separator         |
| `\` (backslash)       | `_`         | Windows directory separator |
| `:` (colon)           | `-`         | Drive separator on Windows  |
| `*` (asterisk)        | `_star_`    | Wildcard character          |
| `?` (question mark)   | `_`         | Wildcard character          |
| `"` (double quote)    | `'`         | Shell/filesystem issues     |
| `<` `>` (brackets)    | `(` `)`     | Shell redirection           |
| `                     | ` (pipe)    | `_`                         | Shell pipe operator |

### Whitespace Normalization

- Leading and trailing whitespace is trimmed
- Tabs, newlines, and carriage returns are converted to spaces
- Multiple consecutive spaces are collapsed to single spaces

### Special Cases

- **Empty album names** → `Unknown_Album_Empty`
- **Whitespace-only names** → `Unknown_Album_Whitespace`
- **Non-printable characters only** → `Unknown_Album_NonPrintable_Nchars`
- **Long names (>100 chars)** → Truncated to 97 characters + "..."

## User Feedback

When album names are modified, ibiRecovery provides clear feedback:

```
Extracting album: My/Problematic*Album?Name (15 files)
  📝 Album name sanitized: 'My/Problematic*Album?Name' → 'My_Problematic_star_Album_Name'
```

## Benefits

1. **Maximum Preservation**: Keeps as much of the original name as possible
2. **Cross-Platform Compatibility**: Works on Windows, macOS, and Linux
3. **Clear Feedback**: Users see exactly what changes were made
4. **Unique Identifiers**: Different types of invalid names get distinct fallback names
5. **No Data Loss**: Every album gets extracted, even with problematic names

## Examples

### Character Replacement

- `"Family Photos/Hawaii 2020"` → `"Family Photos_Hawaii 2020"`
- `"Mom's *Special* Moments"` → `"Mom's _star_Special_star_ Moments"`

### Whitespace Handling

- `"  Album Name  "` → `"Album Name"`
- `"Album\t\tName"` → `"Album Name"`

### Edge Cases

- `""` (empty) → `"Unknown_Album_Empty"`
- `"   "` (spaces only) → `"Unknown_Album_Whitespace"`
- `"!@#$%"` (special chars only) → `"Unknown_Album_NonPrintable_5chars"`

This approach ensures that all your precious photos are recovered with meaningful, filesystem-safe organization while preserving the intent of your original album names.
