"""
Fixed Asset AI - User Management UI
Admin interface for managing users and client access.

Features:
- Create/edit/disable users
- Assign client access
- View audit logs
- Reset passwords
"""

import streamlit as st
from datetime import datetime
from typing import Optional

from logic.auth import AuthManager, UserRole, validate_password_strength
from logic.login_ui import get_auth_manager, get_current_user, require_permission
from logic.database_manager import get_db


def render_user_management():
    """Render the user management interface."""
    st.markdown("## User Management")

    # Check permission
    user = get_current_user()
    if not user or user.role != UserRole.ADMIN:
        st.error("Access denied. Administrator privileges required.")
        return

    auth = get_auth_manager()

    # Tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "Users", "Client Access", "Create User", "Audit Log"
    ])

    with tab1:
        render_users_list(auth)

    with tab2:
        render_client_access(auth)

    with tab3:
        render_create_user(auth, user.user_id)

    with tab4:
        render_auth_audit_log(auth)


def render_users_list(auth: AuthManager):
    """Render list of all users with management options."""
    st.markdown("### All Users")

    users = auth.get_all_users()

    if not users:
        st.info("No users found.")
        return

    # Display as table with actions
    for user_data in users:
        with st.expander(f"👤 {user_data['full_name']} ({user_data['username']})"):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**Email:** {user_data['email']}")
                st.markdown(f"**Role:** {user_data['role'].title()}")
                st.markdown(f"**Status:** {'Active' if user_data['is_active'] else 'Disabled'}")
                if user_data['last_login']:
                    st.markdown(f"**Last Login:** {user_data['last_login']}")

            with col2:
                # Quick actions
                if user_data['is_active']:
                    if st.button("Disable", key=f"disable_{user_data['user_id']}"):
                        auth.update_user(user_data['user_id'], is_active=False)
                        st.success("User disabled")
                        st.rerun()
                else:
                    if st.button("Enable", key=f"enable_{user_data['user_id']}"):
                        auth.update_user(user_data['user_id'], is_active=True)
                        st.success("User enabled")
                        st.rerun()

            # Edit form
            with st.form(f"edit_user_{user_data['user_id']}"):
                st.markdown("**Edit User**")

                new_email = st.text_input("Email", value=user_data['email'])
                new_full_name = st.text_input("Full Name", value=user_data['full_name'])
                new_role = st.selectbox(
                    "Role",
                    options=["admin", "manager", "staff", "readonly"],
                    index=["admin", "manager", "staff", "readonly"].index(user_data['role'])
                )

                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("Update"):
                        auth.update_user(
                            user_data['user_id'],
                            email=new_email,
                            full_name=new_full_name,
                            role=new_role
                        )
                        st.success("User updated")
                        st.rerun()

            # Password reset
            st.markdown("**Reset Password**")
            new_password = st.text_input(
                "New Password",
                type="password",
                key=f"pwd_{user_data['user_id']}"
            )
            if st.button("Reset Password", key=f"reset_pwd_{user_data['user_id']}"):
                if new_password:
                    current_user = get_current_user()
                    success, msg = auth.reset_password(
                        user_data['user_id'],
                        new_password,
                        current_user.user_id
                    )
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.error("Please enter a new password")


def render_client_access(auth: AuthManager):
    """Render client access management."""
    st.markdown("### Client Access Management")

    db = get_db()

    # Get all users and clients
    users = auth.get_all_users()
    clients = db.get_all_clients(active_only=False)

    if not users:
        st.info("No users found.")
        return

    if not clients:
        st.info("No clients found. Create a client first.")
        return

    # Select user
    user_options = {f"{u['full_name']} ({u['username']})": u['user_id'] for u in users}
    selected_user_name = st.selectbox("Select User", options=list(user_options.keys()))
    selected_user_id = user_options[selected_user_name]

    # Get selected user's role
    selected_user = next((u for u in users if u['user_id'] == selected_user_id), None)
    if selected_user and selected_user['role'] == 'admin':
        st.info("Admins automatically have access to all clients.")
        return

    # Show current access
    st.markdown("#### Current Client Access")

    accessible_clients = auth.get_user_clients(selected_user_id)
    accessible_ids = {c['client_id'] for c in accessible_clients}

    # Display as checkboxes
    with st.form("client_access_form"):
        st.markdown("Select clients this user can access:")

        selected_clients = []
        for client in clients:
            is_checked = client['client_id'] in accessible_ids
            if st.checkbox(
                f"{client['client_name']}",
                value=is_checked,
                key=f"client_access_{selected_user_id}_{client['client_id']}"
            ):
                selected_clients.append(client['client_id'])

        if st.form_submit_button("Update Access"):
            current_user = get_current_user()

            # Revoke access for unchecked clients
            for client in clients:
                if client['client_id'] in accessible_ids and client['client_id'] not in selected_clients:
                    auth.revoke_client_access(selected_user_id, client['client_id'])

            # Grant access for newly checked clients
            for client_id in selected_clients:
                if client_id not in accessible_ids:
                    auth.grant_client_access(
                        selected_user_id,
                        client_id,
                        current_user.user_id
                    )

            st.success("Client access updated")
            st.rerun()


def render_create_user(auth: AuthManager, created_by: int):
    """Render create user form."""
    st.markdown("### Create New User")

    with st.form("create_user_form"):
        username = st.text_input("Username", placeholder="john.smith")
        email = st.text_input("Email", placeholder="john.smith@company.com")
        full_name = st.text_input("Full Name", placeholder="John Smith")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")

        role = st.selectbox(
            "Role",
            options=["staff", "manager", "admin", "readonly"],
            help="Staff: Process assets | Manager: Approve exports | Admin: Full access | Read-only: View only"
        )

        st.markdown("""
        **Password Requirements:**
        - At least 8 characters
        - One uppercase letter
        - One lowercase letter
        - One digit
        - One special character (!@#$%^&*()_+-=[]{}|;:,.<>?)
        """)

        submitted = st.form_submit_button("Create User", use_container_width=True)

        if submitted:
            # Validation
            errors = []

            if not username:
                errors.append("Username is required")
            if not email:
                errors.append("Email is required")
            if not full_name:
                errors.append("Full name is required")
            if not password:
                errors.append("Password is required")
            if password != confirm_password:
                errors.append("Passwords don't match")

            if errors:
                for error in errors:
                    st.error(error)
            else:
                success, msg, user_id = auth.create_user(
                    username=username,
                    email=email,
                    password=password,
                    full_name=full_name,
                    role=role,
                    created_by=created_by
                )

                if success:
                    st.success(f"User created successfully! (ID: {user_id})")
                    st.info("Don't forget to assign client access.")
                else:
                    st.error(msg)


def render_auth_audit_log(auth: AuthManager):
    """Render authentication audit log."""
    st.markdown("### Authentication Audit Log")

    db = get_db()

    # Query audit log
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    timestamp, username, action, success, details,
                    ip_address
                FROM auth_audit_log
                ORDER BY timestamp DESC
                LIMIT 100
            """)

            rows = cursor.fetchall()

            if not rows:
                st.info("No audit log entries found.")
                return

            # Display as table
            import pandas as pd

            df = pd.DataFrame(rows, columns=[
                'Timestamp', 'Username', 'Action', 'Success', 'Details', 'IP Address'
            ])

            # Format success as emoji
            df['Success'] = df['Success'].apply(lambda x: '✅' if x else '❌')

            st.dataframe(df, use_container_width=True)

            # Download option
            csv = df.to_csv(index=False)
            st.download_button(
                "Download Audit Log",
                csv,
                "auth_audit_log.csv",
                "text/csv"
            )

    except Exception as e:
        st.error(f"Error loading audit log: {str(e)}")


def render_security_settings():
    """Render security settings (session timeout, etc.)."""
    st.markdown("### Security Settings")

    st.info("""
    **Current Settings:**
    - Session timeout: 30 minutes of inactivity
    - Max session duration: 8 hours
    - Failed login lockout: 5 attempts (15 min lockout)
    - Password requirements: 8+ chars, mixed case, digits, special chars

    These settings can be customized via environment variables:
    - `SESSION_TIMEOUT_MINUTES`: Inactivity timeout
    - `AUTH_ENABLED`: Set to 'false' to disable authentication
    """)
