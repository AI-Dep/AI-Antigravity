# Security & Authentication Guide

## Overview

Fixed Asset AI now includes a comprehensive authentication system designed for accounting firms with strict governance requirements.

## Features

### User Authentication
- **Secure password hashing** using SHA-256 with random salt
- **Session management** with configurable timeout
- **Account lockout** after 5 failed login attempts (15-minute lockout)
- **Login audit trail** for all authentication events

### Role-Based Access Control (RBAC)
Four user roles with different permission levels:

| Role | Permissions |
|------|-------------|
| **Admin** | Full access: manage users, all clients, view audit logs |
| **Manager** | Approve exports, process assets for assigned clients |
| **Staff** | Process assets for assigned clients |
| **Read-only** | View access only |

### Client Data Isolation
- Users can only access clients explicitly assigned to them
- Admins automatically have access to all clients
- Per-user client access mapping with audit trail

### Session Security
- 30-minute inactivity timeout (configurable)
- 8-hour maximum session duration
- Secure session tokens (256-bit random)
- Session invalidation on logout

## Quick Start

### 1. First Run Setup
On first run with no users, you'll see an initial setup screen:
1. Enter your details (name, email, password)
2. Create the admin account
3. Log in with your new credentials

### 2. Adding Users
1. Go to **Manage** > **Users**
2. Click **Create User** tab
3. Fill in user details and assign a role
4. Assign client access in the **Client Access** tab

### 3. Disabling Authentication (Development Only)
For local development, you can disable authentication:
```bash
AUTH_ENABLED=false
```
Add this to your `.env` file.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_ENABLED` | `true` | Enable/disable authentication |
| `SESSION_TIMEOUT_MINUTES` | `30` | Inactivity timeout |
| `INITIAL_ADMIN_PASSWORD` | (random) | Initial admin password |

### Password Requirements
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)

## Security Best Practices

### For Accounting Firms

1. **Use strong passwords**: Enforce complex passwords for all users
2. **Regular access reviews**: Periodically review user access to clients
3. **Session timeouts**: Keep timeout short (15-30 minutes) for sensitive data
4. **Audit log monitoring**: Review authentication logs for suspicious activity
5. **Principle of least privilege**: Assign minimum required permissions

### For Deployment

1. **Always use HTTPS** in production
2. **Enable authentication** (`AUTH_ENABLED=true`)
3. **Set strong initial admin password** via environment variable
4. **Regular backups** of the SQLite database
5. **Network-level security** (firewall, VPN) for additional protection

## Audit Trail

The authentication system logs:
- Login attempts (success/failure)
- Account lockouts
- Password changes
- User creation/modification
- Client access changes
- Logouts

View the audit log in **Manage** > **Users** > **Audit Log** tab.

## Compliance Considerations

This authentication system provides:

| Requirement | Implementation |
|-------------|----------------|
| **Access Control** | Role-based permissions, client isolation |
| **Audit Trail** | Comprehensive logging of all auth events |
| **Session Management** | Timeout, secure tokens, lockout |
| **Password Security** | Hashing, strength requirements |
| **Data Segregation** | Per-client access control |

### What's Still Needed for Full Compliance

For SOC 2 or similar compliance:
- **MFA**: Multi-factor authentication (not yet implemented)
- **SSO**: Single sign-on integration (not yet implemented)
- **Encryption at rest**: Database encryption (recommended for production)
- **Regular penetration testing**: Professional security assessment
- **Security policies**: Written policies and procedures

## Troubleshooting

### "Account locked" message
Account is locked after 5 failed login attempts. Wait 15 minutes or have an admin reset your password.

### Session expired unexpectedly
Check `SESSION_TIMEOUT_MINUTES` setting. Default is 30 minutes of inactivity.

### Can't access a client
Check with admin that you have been granted access to that client.

### Login page not showing
Check that `AUTH_ENABLED` is set to `true` (default).

## Technical Architecture

```
                                   ┌─────────────────┐
                                   │   Streamlit UI  │
                                   └────────┬────────┘
                                            │
                                   ┌────────▼────────┐
                                   │   login_ui.py   │
                                   │  (Login Form)   │
                                   └────────┬────────┘
                                            │
                                   ┌────────▼────────┐
                                   │    auth.py      │
                                   │ (Auth Manager)  │
                                   └────────┬────────┘
                                            │
┌───────────────┬───────────────┬───────────┼───────────────┐
│               │               │           │               │
▼               ▼               ▼           ▼               ▼
┌─────┐    ┌─────────┐    ┌──────────┐  ┌────────┐  ┌──────────┐
│users│    │user_    │    │user_     │  │auth_   │  │sessions  │
│table│    │sessions │    │client_   │  │audit_  │  │(existing)│
└─────┘    └─────────┘    │access    │  │log     │  └──────────┘
                          └──────────┘  └────────┘
```

## Database Tables

The authentication system creates these tables:

- `users` - User accounts with hashed passwords
- `user_sessions` - Active login sessions
- `user_client_access` - User-to-client mapping
- `auth_audit_log` - Authentication audit trail

These are created automatically on first run.
