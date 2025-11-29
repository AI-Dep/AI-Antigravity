"""
Fixed Asset AI - Login UI Component
Streamlit-based authentication interface.

Features:
- Login form with username/password
- Session management via cookies
- Logout functionality
- Password change dialog
- Session timeout warnings
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, Tuple
import os

# Import auth module
from logic.auth import AuthManager, User, UserRole, get_role_permissions, SESSION_TIMEOUT_MINUTES
from logic.database_manager import get_db


def get_auth_manager() -> AuthManager:
    """Get or create AuthManager instance."""
    if 'auth_manager' not in st.session_state:
        db = get_db()
        st.session_state.auth_manager = AuthManager(db)
    return st.session_state.auth_manager


def is_auth_enabled() -> bool:
    """
    Check if authentication is enabled.

    Auth can be disabled for local development by setting:
    AUTH_ENABLED=false in environment

    Returns:
        True if authentication is enabled
    """
    return os.getenv("AUTH_ENABLED", "true").lower() != "false"


def get_current_user() -> Optional[User]:
    """
    Get currently logged in user.

    Returns:
        User object if logged in, None otherwise
    """
    if not is_auth_enabled():
        # Return mock admin user when auth is disabled
        return User(
            user_id=0,
            username="dev_user",
            email="dev@localhost",
            full_name="Development User",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(),
            last_login=datetime.now()
        )

    # Check session state for user
    if 'current_user' in st.session_state and st.session_state.current_user:
        return st.session_state.current_user

    # Check for session token
    session_token = st.session_state.get('session_token')
    if session_token:
        auth = get_auth_manager()
        is_valid, user = auth.validate_session(session_token)
        if is_valid and user:
            st.session_state.current_user = user
            return user
        else:
            # Invalid session - clear
            st.session_state.pop('session_token', None)
            st.session_state.pop('current_user', None)

    return None


def require_auth() -> Optional[User]:
    """
    Require authentication to proceed.
    Shows login form if not authenticated.

    Returns:
        User object if authenticated, None if showing login form
    """
    if not is_auth_enabled():
        return get_current_user()

    user = get_current_user()
    if user:
        return user

    # Show login form
    show_login_page()
    return None


def show_login_page():
    """Display the login page."""
    st.markdown("""
    <style>
    .login-container {
        max-width: 400px;
        margin: 0 auto;
        padding: 2rem;
    }
    .login-title {
        text-align: center;
        margin-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("### Fixed Asset AI")
        st.markdown("**Secure Login**")
        st.markdown("---")

        # Check for initial setup
        auth = get_auth_manager()
        users = auth.get_all_users()

        if not users:
            # No users - show initial setup
            show_initial_setup(auth)
        else:
            # Show login form
            show_login_form(auth)


def show_initial_setup(auth: AuthManager):
    """Show initial admin setup form."""
    st.info("**First Time Setup**\n\nNo users exist. Create the initial administrator account.")

    with st.form("initial_setup_form"):
        st.markdown("#### Create Admin Account")

        full_name = st.text_input("Full Name", placeholder="System Administrator")
        email = st.text_input("Email", placeholder="admin@yourcompany.com")
        password = st.text_input("Password", type="password", placeholder="Strong password required")
        confirm_password = st.text_input("Confirm Password", type="password")

        st.markdown("""
        **Password Requirements:**
        - At least 8 characters
        - One uppercase letter
        - One lowercase letter
        - One digit
        - One special character
        """)

        submitted = st.form_submit_button("Create Admin Account", use_container_width=True)

        if submitted:
            if not full_name or not email or not password:
                st.error("All fields are required")
            elif password != confirm_password:
                st.error("Passwords do not match")
            else:
                success, msg, user_id = auth.create_user(
                    username="admin",
                    email=email,
                    password=password,
                    full_name=full_name,
                    role="admin"
                )

                if success:
                    st.success("Admin account created! Please log in.")
                    st.rerun()
                else:
                    st.error(msg)


def show_login_form(auth: AuthManager):
    """Show the login form."""
    # Check for error/success messages
    if 'login_error' in st.session_state:
        st.error(st.session_state.login_error)
        del st.session_state.login_error

    if 'login_success' in st.session_state:
        st.success(st.session_state.login_success)
        del st.session_state.login_success

    with st.form("login_form"):
        username = st.text_input("Username or Email", placeholder="Enter username or email")
        password = st.text_input("Password", type="password", placeholder="Enter password")

        col1, col2 = st.columns(2)
        with col1:
            remember_me = st.checkbox("Remember me")
        with col2:
            pass  # Could add "Forgot password" link

        submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if not username or not password:
                st.session_state.login_error = "Please enter username and password"
                st.rerun()
            else:
                # Attempt authentication
                success, msg, session_token = auth.authenticate(
                    username=username,
                    password=password,
                    ip_address=None,  # Could get from headers in production
                    user_agent=None
                )

                if success:
                    st.session_state.session_token = session_token
                    st.session_state.login_time = datetime.now()

                    # Validate session to get user
                    is_valid, user = auth.validate_session(session_token)
                    if is_valid:
                        st.session_state.current_user = user
                        st.rerun()
                else:
                    st.session_state.login_error = msg
                    st.rerun()

    st.markdown("---")
    st.caption("Contact your administrator if you need access.")


def show_user_menu():
    """Show user menu in sidebar when logged in."""
    user = get_current_user()
    if not user:
        return

    with st.sidebar:
        st.markdown("---")
        st.markdown(f"**Logged in as:** {user.full_name}")
        st.caption(f"Role: {user.role.value.title()}")

        # Session info
        if 'login_time' in st.session_state:
            login_time = st.session_state.login_time
            session_duration = datetime.now() - login_time
            st.caption(f"Session: {int(session_duration.total_seconds() // 60)} min")

        # Session timeout warning
        if 'login_time' in st.session_state:
            elapsed = (datetime.now() - st.session_state.login_time).total_seconds() / 60
            remaining = SESSION_TIMEOUT_MINUTES - elapsed

            if remaining <= 5 and remaining > 0:
                st.warning(f"Session expires in {int(remaining)} minutes")
            elif remaining <= 0:
                st.error("Session expired. Please log in again.")
                logout()
                st.rerun()

        # User actions
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Profile", use_container_width=True):
                st.session_state.show_profile = True

        with col2:
            if st.button("Logout", use_container_width=True):
                logout()
                st.rerun()


def logout():
    """Log out the current user."""
    if 'session_token' in st.session_state:
        auth = get_auth_manager()
        auth.logout(st.session_state.session_token)

    # Clear session state
    keys_to_clear = ['session_token', 'current_user', 'login_time', 'selected_client_id']
    for key in keys_to_clear:
        st.session_state.pop(key, None)


def show_profile_dialog():
    """Show user profile dialog."""
    if not st.session_state.get('show_profile'):
        return

    user = get_current_user()
    if not user:
        return

    with st.sidebar:
        st.markdown("---")
        st.markdown("### Profile")

        st.markdown(f"**Name:** {user.full_name}")
        st.markdown(f"**Username:** {user.username}")
        st.markdown(f"**Email:** {user.email}")
        st.markdown(f"**Role:** {user.role.value.title()}")

        if user.last_login:
            st.markdown(f"**Last Login:** {user.last_login.strftime('%Y-%m-%d %H:%M')}")

        # Change password form
        with st.expander("Change Password"):
            with st.form("change_password_form"):
                current_password = st.text_input("Current Password", type="password")
                new_password = st.text_input("New Password", type="password")
                confirm_password = st.text_input("Confirm New Password", type="password")

                if st.form_submit_button("Change Password"):
                    if not current_password or not new_password:
                        st.error("All fields required")
                    elif new_password != confirm_password:
                        st.error("Passwords don't match")
                    else:
                        auth = get_auth_manager()
                        success, msg = auth.change_password(
                            user.user_id, current_password, new_password
                        )
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)

        if st.button("Close Profile"):
            st.session_state.show_profile = False
            st.rerun()


def require_permission(permission: str) -> bool:
    """
    Check if current user has a specific permission.

    Args:
        permission: Permission to check

    Returns:
        True if user has permission
    """
    user = get_current_user()
    if not user:
        return False

    permissions = get_role_permissions(user.role)
    return permissions.get(permission, False)


def require_role(min_role: UserRole) -> bool:
    """
    Check if current user has minimum role level.

    Args:
        min_role: Minimum required role

    Returns:
        True if user meets requirement
    """
    user = get_current_user()
    if not user:
        return False

    role_hierarchy = {
        UserRole.READONLY: 0,
        UserRole.STAFF: 1,
        UserRole.MANAGER: 2,
        UserRole.ADMIN: 3
    }

    user_level = role_hierarchy.get(user.role, 0)
    required_level = role_hierarchy.get(min_role, 0)

    return user_level >= required_level


def get_accessible_clients() -> list:
    """
    Get list of clients accessible to current user.

    Returns:
        List of client dicts
    """
    user = get_current_user()
    if not user:
        return []

    auth = get_auth_manager()
    return auth.get_user_clients(user.user_id)


def has_client_access(client_id: int) -> bool:
    """
    Check if current user has access to a specific client.

    Args:
        client_id: Client ID to check

    Returns:
        True if user has access
    """
    user = get_current_user()
    if not user:
        return False

    auth = get_auth_manager()
    return auth.has_client_access(user.user_id, client_id)


def show_client_selector() -> Optional[int]:
    """
    Show client selector for multi-client access.

    Returns:
        Selected client_id or None
    """
    user = get_current_user()
    if not user:
        return None

    clients = get_accessible_clients()

    if not clients:
        st.warning("You don't have access to any clients. Contact your administrator.")
        return None

    # For users with only one client, auto-select
    if len(clients) == 1:
        st.session_state.selected_client_id = clients[0]['client_id']
        return clients[0]['client_id']

    # Show selector
    with st.sidebar:
        st.markdown("---")
        st.markdown("**Select Client**")

        client_options = {c['client_name']: c['client_id'] for c in clients}
        selected_name = st.selectbox(
            "Client",
            options=list(client_options.keys()),
            key="client_selector"
        )

        if selected_name:
            client_id = client_options[selected_name]
            st.session_state.selected_client_id = client_id
            return client_id

    return st.session_state.get('selected_client_id')
