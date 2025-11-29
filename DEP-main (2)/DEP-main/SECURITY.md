# Security Guide

## Overview

This document outlines security best practices and features implemented in the Fixed Asset AI tool.

## API Key Security

### ✅ CRITICAL: Protect Your OpenAI API Key

1. **Never commit your API key to git**
   - Use `.env` file for local development (already in `.gitignore`)
   - Use Streamlit secrets for cloud deployment
   - Never hardcode API keys in source code

2. **Set up your API key securely:**

   ```bash
   # Copy the example file
   cp .env.example .env

   # Edit .env and add your API key
   # This file is gitignored and won't be committed
   ```

3. **For Streamlit Cloud deployment:**
   - Use Streamlit secrets: Settings → Secrets
   - Never paste API keys in public forums or chat

### OpenAI API Key Permissions

We recommend creating a restricted API key with:
- **Usage limits:** Set monthly spending caps in OpenAI dashboard
- **Rate limits:** Configure per-minute request limits
- **Allowed models:** Restrict to `gpt-4o-mini` or similar

Visit: https://platform.openai.com/account/limits

## Cost Controls

### Built-in Protections

1. **Maximum Asset Limit:** 1000 assets per run (configurable)
   - Prevents accidental massive processing
   - Protects against runaway API costs
   - Can be adjusted via `MAX_ASSETS_PER_RUN` in app.py

2. **Cost Estimation:**
   - Displays estimated cost before processing
   - Conservative estimate (assumes 80% need GPT)
   - Real cost often lower due to rule-based matching

3. **Rule-Based Matching First:**
   - ~60-70% of assets matched by rules (no API cost)
   - Only ambiguous cases sent to GPT
   - Reduces API usage significantly

### Monitoring Your Usage

1. **Check OpenAI Dashboard:**
   - Visit https://platform.openai.com/usage
   - Monitor daily/monthly usage
   - Set up billing alerts

2. **Review Error Logs:**
   - Check `logs/app_errors.log` for issues
   - Look for repeated API failures
   - Monitor classification statistics

## Data Privacy

### What Data is Sent to OpenAI?

**✅ Sent to OpenAI API:**
- Asset descriptions (sanitized, no PII)
- Client-provided category names
- Cost amounts (numeric values only)
- Location (optional, can be disabled)

**🔒 NEVER Sent to OpenAI:**
- Asset IDs or unique identifiers
- Client names or identifiers
- Acquisition/in-service dates
- Employee names or personal information
- Internal file paths
- API keys or credentials

### Data Sanitization

All descriptions are sanitized before sending to OpenAI:
- Email addresses removed
- Phone numbers redacted
- URLs cleaned
- Special characters normalized
- PII patterns filtered

### Privacy Settings

Users can control what data is shared:
1. **Location Data:** Can be excluded from OpenAI requests
2. **Logging:** Sensitive data redacted from downloadable logs
3. **Session Data:** Cleared when user closes the app

## Application Security

### Implemented Protections

1. **CSRF Protection:** ✅ Enabled (Streamlit default)
2. **Input Validation:** ✅ Client IDs sanitized and validated
3. **Path Sanitization:** ✅ Prevents directory traversal attacks
4. **Error Handling:** ✅ No stack traces exposed to users
5. **Secure Logging:** ✅ Sensitive data redacted from logs

### Secure Error Logging

- Detailed errors logged to `logs/app_errors.log` (server-side only)
- Users see generic messages with error IDs
- No exposure of internal paths, code, or package versions
- Log files excluded from git (`.gitignore`)

### File Upload Security

- **Allowed formats:** Only `.xlsx` and `.xls` files
- **Size limits:** Enforced by Streamlit (200MB default)
- **Asset count limits:** Maximum 1000 assets per run
- **Path validation:** Filenames sanitized before saving

## Compliance Considerations

### Tax Data Handling

This tool processes tax-related financial information:

1. **Data Retention:**
   - Session data cleared when user closes app
   - No data stored on Streamlit Cloud by default
   - Local deployments: ensure proper data handling

2. **Audit Trail:**
   - Classification decisions logged
   - Override records saved with timestamps
   - RPA automation includes approval records

3. **Access Control:**
   - Consider deploying behind authentication
   - Use Streamlit Cloud Teams for user management
   - Implement IP restrictions if needed

### OpenAI Data Retention

**Important:** OpenAI's data retention policy (as of 2024):
- API data NOT used for model training (Enterprise tier)
- Data retained for 30 days for abuse monitoring
- Can be deleted upon request

For highly sensitive data:
- Consider on-premise LLM deployment
- Use OpenAI's zero-retention API options
- Review OpenAI's Enterprise Agreement

## Security Checklist

Before deploying to production:

- [ ] API key stored in `.env` or Streamlit secrets (not in code)
- [ ] `.env` file in `.gitignore` (verify it's not in git)
- [ ] Monthly spending limit set in OpenAI dashboard
- [ ] Asset processing limit configured appropriately
- [ ] Review what data is sent to OpenAI
- [ ] Test with sample data before using real client data
- [ ] Error logs directory (`logs/`) excluded from git
- [ ] Understand data retention policies
- [ ] Consider deployment behind authentication
- [ ] Regular security updates and dependency scanning

## Incident Response

If you suspect an API key compromise:

1. **Immediately revoke the key** at https://platform.openai.com/api-keys
2. **Create a new key** with appropriate limits
3. **Review usage logs** for unauthorized activity
4. **Check billing** for unexpected charges
5. **Update `.env` or secrets** with new key
6. **Rotate any other potentially exposed secrets**

## Reporting Security Issues

Found a security vulnerability?

1. **Do NOT** open a public GitHub issue
2. Contact the development team privately
3. Provide details: affected version, steps to reproduce
4. Allow time for patch before public disclosure

## Updates and Maintenance

- Regularly update dependencies: `pip install -U -r requirements.txt`
- Monitor OpenAI API announcements for security updates
- Review and update spending limits quarterly
- Audit access logs and usage patterns
- Keep this security guide updated

---

**Last Updated:** 2025-01-21
**Security Rating:** 8.0/10
