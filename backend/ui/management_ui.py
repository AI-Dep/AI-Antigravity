"""
Fixed Asset AI - Management UI
Comprehensive management interface for SQLite database

Provides:
- Audit Trail Dashboard
- Export History Browser
- Classification Manager
- Client Configuration Manager
- Analytics & Reporting Dashboard
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import json
import plotly.express as px
import plotly.graph_objects as go

from .database_manager import get_db

# Import user management (optional - only available if auth module is installed)
try:
    from .user_management_ui import render_user_management
    USER_MANAGEMENT_AVAILABLE = True
except ImportError:
    USER_MANAGEMENT_AVAILABLE = False


class ManagementUI:
    """Management UI for Fixed Asset AI system."""

    def __init__(self):
        self.db = get_db()

    def render(self):
        """Render main management UI."""
        st.title("🔧 System Management")

        # Sidebar navigation
        sections = [
            "📊 Dashboard",
            "📋 Audit Trail",
            "📦 Export History",
            "🏷️ Classifications",
            "👥 Clients",
            "📈 Analytics"
        ]

        # Add user management if available
        if USER_MANAGEMENT_AVAILABLE:
            sections.append("🔐 Users")

        page = st.sidebar.selectbox(
            "Management Section",
            sections
        )

        # Render selected page
        if page == "📊 Dashboard":
            self.render_dashboard()
        elif page == "📋 Audit Trail":
            self.render_audit_trail()
        elif page == "📦 Export History":
            self.render_export_history()
        elif page == "🏷️ Classifications":
            self.render_classifications()
        elif page == "👥 Clients":
            self.render_clients()
        elif page == "📈 Analytics":
            self.render_analytics()
        elif page == "🔐 Users" and USER_MANAGEMENT_AVAILABLE:
            render_user_management()

    # ========================================================================
    # DASHBOARD
    # ========================================================================

    def render_dashboard(self):
        """Render main dashboard with key metrics."""
        st.header("📊 Management Dashboard")

        # Get stats
        stats = self.db.get_dashboard_stats()

        # Top metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Active Clients", stats['total_clients'])

        with col2:
            st.metric("Total Assets", stats['total_assets'])

        with col3:
            st.metric("Total Exports", stats['total_exports'])

        with col4:
            st.metric("Pending Approvals", stats['pending_approvals'],
                     delta=None if stats['pending_approvals'] == 0 else "Needs attention")

        st.markdown("---")

        # Recent activity
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Recent Activity")
            activity = stats.get('recent_activity', [])

            if activity:
                activity_df = pd.DataFrame(activity)
                activity_df['timestamp'] = pd.to_datetime(activity_df['timestamp'])
                activity_df = activity_df.sort_values('timestamp', ascending=False)

                for _, row in activity_df.head(10).iterrows():
                    timestamp = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    action = row['action_type']
                    entity = row['entity_type']
                    desc = row['description']
                    user = row.get('user_name', 'System')

                    st.text(f"{timestamp} | {action} | {entity}")
                    st.caption(f"   {desc} (by {user})")
            else:
                st.info("No recent activity")

        with col2:
            st.subheader("Quick Actions")

            if st.button("🔄 Run Migration", use_container_width=True):
                st.info("Migration will be implemented in the integration phase")

            if st.button("📥 Backup Database", use_container_width=True):
                st.info("Backup functionality coming soon")

            if st.button("🧹 Clean Old Data", use_container_width=True):
                st.info("Cleanup functionality coming soon")

        # Client activity summary
        st.markdown("---")
        st.subheader("Client Activity Summary")

        client_activity = self.db.get_client_activity_report()
        if client_activity:
            df = pd.DataFrame(client_activity)
            df['last_export_date'] = pd.to_datetime(df['last_export_date'])
            df = df.sort_values('total_exports', ascending=False)

            st.dataframe(
                df[['client_name', 'total_exports', 'total_approvals', 'total_assets', 'last_export_date']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No client activity data")

    # ========================================================================
    # AUDIT TRAIL
    # ========================================================================

    def render_audit_trail(self):
        """Render audit trail dashboard."""
        st.header("📋 Audit Trail")

        # Filters
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            action_filter = st.selectbox(
                "Action Type",
                ["All", "CREATE", "UPDATE", "DELETE", "EXPORT", "APPROVE", "REJECT"]
            )

        with col2:
            entity_filter = st.selectbox(
                "Entity Type",
                ["All", "asset", "classification", "export", "approval", "client", "override"]
            )

        with col3:
            clients = self.db.get_all_clients(active_only=False)
            client_options = ["All"] + [c['client_name'] for c in clients]
            client_filter = st.selectbox("Client", client_options)

        with col4:
            limit = st.number_input("Limit", min_value=10, max_value=1000, value=100, step=10)

        # Get audit log
        action = None if action_filter == "All" else action_filter
        entity = None if entity_filter == "All" else entity_filter
        client_id = None
        if client_filter != "All":
            client_id = next((c['client_id'] for c in clients if c['client_name'] == client_filter), None)

        audit_log = self.db.get_audit_log(
            entity_type=entity,
            client_id=client_id,
            limit=limit
        )

        # Filter by action if needed
        if action:
            audit_log = [a for a in audit_log if a['action_type'] == action]

        if audit_log:
            # Convert to DataFrame
            df = pd.DataFrame(audit_log)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp', ascending=False)

            # Display summary
            st.info(f"Showing {len(df)} audit entries")

            # Display table
            display_cols = ['timestamp', 'action_type', 'entity_type', 'user_name', 'description']
            display_df = df[display_cols].copy()
            display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )

            # Detailed view
            st.markdown("---")
            st.subheader("Detailed View")

            selected_index = st.selectbox(
                "Select entry to view details",
                range(len(df)),
                format_func=lambda i: f"{df.iloc[i]['timestamp']} - {df.iloc[i]['action_type']} - {df.iloc[i]['description']}"
            )

            if selected_index is not None:
                entry = df.iloc[selected_index]

                col1, col2 = st.columns(2)

                with col1:
                    st.write("**Audit ID:**", entry['audit_id'])
                    st.write("**Timestamp:**", entry['timestamp'])
                    st.write("**Action:**", entry['action_type'])
                    st.write("**Entity:**", f"{entry['entity_type']} (ID: {entry.get('entity_id', 'N/A')})")

                with col2:
                    st.write("**User:**", entry.get('user_name', 'N/A'))
                    st.write("**Email:**", entry.get('user_email', 'N/A'))
                    st.write("**IP Address:**", entry.get('ip_address', 'N/A'))
                    st.write("**Session:**", entry.get('session_id', 'N/A'))

                st.write("**Description:**", entry['description'])

                if entry.get('old_values'):
                    st.write("**Old Values:**")
                    st.json(entry['old_values'])

                if entry.get('new_values'):
                    st.write("**New Values:**")
                    st.json(entry['new_values'])

        else:
            st.warning("No audit entries found")

    # ========================================================================
    # EXPORT HISTORY
    # ========================================================================

    def render_export_history(self):
        """Render export history browser."""
        st.header("📦 Export History")

        # Filters
        col1, col2, col3 = st.columns(3)

        with col1:
            clients = self.db.get_all_clients(active_only=False)
            client_options = ["All"] + [c['client_name'] for c in clients]
            client_filter = st.selectbox("Client", client_options)

        with col2:
            years = list(range(datetime.now().year, datetime.now().year - 10, -1))
            year_filter = st.selectbox("Tax Year", ["All"] + years)

        with col3:
            status_filter = st.selectbox(
                "Approval Status",
                ["All", "PENDING", "APPROVED", "REJECTED"]
            )

        # Get exports
        exports = self.db.get_recent_exports(limit=100)

        # Apply filters
        if client_filter != "All":
            exports = [e for e in exports if e['client_name'] == client_filter]

        if year_filter != "All":
            exports = [e for e in exports if e['tax_year'] == year_filter]

        if status_filter != "All":
            exports = [e for e in exports if e.get('approval_status') == status_filter]

        if exports:
            df = pd.DataFrame(exports)
            df['export_date'] = pd.to_datetime(df['export_date'])
            df = df.sort_values('export_date', ascending=False)

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Exports", len(df))

            with col2:
                total_assets = df['total_assets'].sum()
                st.metric("Total Assets", f"{total_assets:,}")

            with col3:
                total_cost = df['total_cost'].sum()
                st.metric("Total Cost", f"${total_cost:,.0f}")

            with col4:
                total_deduction = df['year1_total_deduction'].sum()
                st.metric("Total Y1 Deduction", f"${total_deduction:,.0f}")

            st.markdown("---")

            # Display table
            display_cols = [
                'export_date', 'client_name', 'tax_year', 'total_assets',
                'total_cost', 'year1_total_deduction', 'approval_status', 'rpa_status'
            ]

            display_df = df[[col for col in display_cols if col in df.columns]].copy()
            display_df['export_date'] = display_df['export_date'].dt.strftime('%Y-%m-%d')

            # Format currency columns
            if 'total_cost' in display_df.columns:
                display_df['total_cost'] = display_df['total_cost'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")
            if 'year1_total_deduction' in display_df.columns:
                display_df['year1_total_deduction'] = display_df['year1_total_deduction'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )

            # Export details
            st.markdown("---")
            st.subheader("Export Details")

            selected_export = st.selectbox(
                "Select export to view details",
                range(len(df)),
                format_func=lambda i: f"{df.iloc[i]['export_date'].strftime('%Y-%m-%d')} - {df.iloc[i]['client_name']} - Tax Year {df.iloc[i]['tax_year']}"
            )

            if selected_export is not None:
                export = df.iloc[selected_export]

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.write("**Export ID:**", export['export_id'])
                    st.write("**Client:**", export['client_name'])
                    st.write("**Tax Year:**", export['tax_year'])
                    st.write("**Export Date:**", export['export_date'].strftime('%Y-%m-%d %H:%M'))

                with col2:
                    st.write("**Total Assets:**", f"{export['total_assets']:,}")
                    st.write("**Total Cost:**", f"${export['total_cost']:,.2f}" if pd.notna(export['total_cost']) else "N/A")
                    st.write("**Section 179:**", f"${export.get('total_section_179', 0):,.2f}")
                    st.write("**Bonus Depreciation:**", f"${export.get('total_bonus', 0):,.2f}")

                with col3:
                    st.write("**Approval Status:**", export.get('approval_status', 'N/A'))
                    st.write("**RPA Status:**", export.get('rpa_status', 'N/A'))
                    st.write("**Approver:**", export.get('approver_name', 'N/A'))
                    st.write("**Y1 Deduction:**", f"${export.get('year1_total_deduction', 0):,.2f}")

                # Show assets in this export
                if st.checkbox("Show assets in this export"):
                    export_assets = self.db.get_export_assets(export['export_id'])
                    if export_assets:
                        assets_df = pd.DataFrame(export_assets)
                        st.dataframe(assets_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No asset details available")

        else:
            st.warning("No exports found")

    # ========================================================================
    # CLASSIFICATIONS
    # ========================================================================

    def render_classifications(self):
        """Render classification manager."""
        st.header("🏷️ Classification Manager")

        tab1, tab2, tab3 = st.tabs(["📊 Overview", "🔍 Search", "➕ Overrides"])

        with tab1:
            self._render_classification_overview()

        with tab2:
            self._render_classification_search()

        with tab3:
            self._render_overrides_manager()

    def _render_classification_overview(self):
        """Render classification overview."""
        st.subheader("Classification Overview")

        # Get classification stats
        query = """
            SELECT
                source,
                COUNT(*) as total,
                AVG(confidence_score) as avg_confidence,
                COUNT(CASE WHEN confidence_score >= 0.9 THEN 1 END) as high_confidence,
                COUNT(CASE WHEN confidence_score < 0.7 THEN 1 END) as low_confidence
            FROM classifications
            WHERE classification_date >= date('now', '-30 days')
            GROUP BY source
        """

        stats = self.db.execute_query(query)

        if stats:
            df = pd.DataFrame(stats)

            # Display metrics
            col1, col2, col3 = st.columns(3)

            with col1:
                total = df['total'].sum()
                st.metric("Total Classifications (30d)", f"{total:,}")

            with col2:
                avg_confidence = df['avg_confidence'].mean()
                st.metric("Avg Confidence", f"{avg_confidence:.1%}" if pd.notna(avg_confidence) else "N/A")

            with col3:
                high_conf = df['high_confidence'].sum()
                pct = (high_conf / total * 100) if total > 0 else 0
                st.metric("High Confidence", f"{high_conf:,} ({pct:.0f}%)")

            # Chart by source
            fig = px.bar(
                df,
                x='source',
                y='total',
                title="Classifications by Source (Last 30 Days)",
                labels={'source': 'Source', 'total': 'Count'}
            )
            st.plotly_chart(fig, use_container_width=True)

            # Confidence distribution
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(name='High (>=0.9)', x=df['source'], y=df['high_confidence']))
            fig2.add_trace(go.Bar(name='Low (<0.7)', x=df['source'], y=df['low_confidence']))
            fig2.update_layout(
                title="Confidence Distribution by Source",
                barmode='group',
                xaxis_title="Source",
                yaxis_title="Count"
            )
            st.plotly_chart(fig2, use_container_width=True)

        else:
            st.info("No classification data available")

    def _render_classification_search(self):
        """Render classification search."""
        st.subheader("Search Classifications")

        search_term = st.text_input("Search asset text or description", "")

        if search_term:
            query = """
                SELECT
                    c.classification_id,
                    c.asset_text,
                    c.classification_class,
                    c.classification_life,
                    c.classification_method,
                    c.source,
                    c.confidence_score,
                    c.classification_date
                FROM classifications c
                WHERE c.asset_text LIKE ? OR c.asset_description LIKE ?
                ORDER BY c.classification_date DESC
                LIMIT 50
            """

            results = self.db.execute_query(query, (f"%{search_term}%", f"%{search_term}%"))

            if results:
                df = pd.DataFrame(results)
                df['classification_date'] = pd.to_datetime(df['classification_date'])

                st.info(f"Found {len(df)} classifications")

                # Display results
                for _, row in df.iterrows():
                    with st.expander(f"{row['asset_text'][:80]}... - {row['classification_class']}"):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.write("**Class:**", row['classification_class'])
                            st.write("**Life:**", f"{row['classification_life']} years")
                            st.write("**Method:**", row['classification_method'])

                        with col2:
                            st.write("**Source:**", row['source'])
                            st.write("**Confidence:**", f"{row['confidence_score']:.1%}" if pd.notna(row['confidence_score']) else "N/A")
                            st.write("**Date:**", row['classification_date'].strftime('%Y-%m-%d %H:%M'))

                        st.write("**Full Text:**", row['asset_text'])

            else:
                st.warning("No results found")

    def _render_overrides_manager(self):
        """Render overrides manager."""
        st.subheader("Override Rules")

        # Get overrides
        overrides = self.db.get_overrides(active_only=False)

        if overrides:
            df = pd.DataFrame(overrides)

            # Summary
            total = len(df)
            active = len(df[df['is_active'] == 1])
            st.info(f"Total Overrides: {total} | Active: {active}")

            # Display table
            display_cols = [
                'override_id', 'override_type', 'external_asset_id', 'category_name',
                'override_class', 'override_life', 'priority', 'is_active'
            ]

            display_df = df[[col for col in display_cols if col in df.columns]].copy()

            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # Add new override
            st.markdown("---")
            st.subheader("Add New Override")

            with st.form("new_override"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    override_type = st.selectbox(
                        "Override Type",
                        ["asset_id", "client_category", "description_pattern"]
                    )

                with col2:
                    if override_type == "asset_id":
                        identifier = st.text_input("Asset ID")
                    elif override_type == "client_category":
                        identifier = st.text_input("Category Name")
                    else:
                        identifier = st.text_input("Description Pattern")

                with col3:
                    priority = st.number_input("Priority", min_value=0, max_value=100, value=10)

                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    override_class = st.text_input("Class", value="Office Equipment")

                with col2:
                    override_life = st.number_input("Life (years)", min_value=1, max_value=50, value=7)

                with col3:
                    override_method = st.selectbox("Method", ["MACRS GDS", "MACRS ADS", "Straight Line"])

                with col4:
                    override_convention = st.selectbox("Convention", ["HY", "MQ", "MM"])

                col1, col2 = st.columns(2)

                with col1:
                    is_bonus = st.checkbox("Bonus Eligible", value=True)

                with col2:
                    is_qip = st.checkbox("QIP", value=False)

                submitted = st.form_submit_button("Add Override")

                if submitted and identifier:
                    kwargs = {
                        'priority': priority,
                        'is_bonus_eligible': is_bonus,
                        'is_qip': is_qip,
                        'is_active': True,
                        'created_by': 'ui'
                    }

                    if override_type == "asset_id":
                        kwargs['external_asset_id'] = identifier
                    elif override_type == "client_category":
                        kwargs['category_name'] = identifier
                    else:
                        kwargs['description_pattern'] = identifier

                    try:
                        self.db.create_override(
                            override_type=override_type,
                            override_class=override_class,
                            override_life=override_life,
                            override_method=override_method,
                            override_convention=override_convention,
                            **kwargs
                        )
                        st.success("Override added successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error adding override: {str(e)}")

        else:
            st.info("No overrides found")

    # ========================================================================
    # CLIENTS
    # ========================================================================

    def render_clients(self):
        """Render client management."""
        st.header("👥 Client Management")

        tab1, tab2 = st.tabs(["📋 Client List", "➕ Add Client"])

        with tab1:
            self._render_client_list()

        with tab2:
            self._render_add_client()

    def _render_client_list(self):
        """Render client list."""
        st.subheader("Client List")

        clients = self.db.get_all_clients(active_only=False)

        if clients:
            df = pd.DataFrame(clients)

            # Summary
            total = len(df)
            active = len(df[df['active'] == 1])
            st.info(f"Total Clients: {total} | Active: {active}")

            # Display table
            display_cols = [
                'client_id', 'client_name', 'client_code', 'contact_name',
                'contact_email', 'active', 'rpa_enabled', 'created_at'
            ]

            display_df = df[[col for col in display_cols if col in df.columns]].copy()
            display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d')

            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # Client details
            st.markdown("---")
            st.subheader("Client Details")

            selected_client = st.selectbox(
                "Select client",
                range(len(df)),
                format_func=lambda i: f"{df.iloc[i]['client_name']} ({df.iloc[i]['client_code']})"
            )

            if selected_client is not None:
                client = df.iloc[selected_client]

                col1, col2 = st.columns(2)

                with col1:
                    st.write("**Client ID:**", client['client_id'])
                    st.write("**Name:**", client['client_name'])
                    st.write("**Code:**", client['client_code'])
                    st.write("**Contact:**", client.get('contact_name', 'N/A'))
                    st.write("**Email:**", client.get('contact_email', 'N/A'))

                with col2:
                    st.write("**Active:**", "Yes" if client['active'] else "No")
                    st.write("**RPA Enabled:**", "Yes" if client.get('rpa_enabled') else "No")
                    st.write("**Import Automation:**", "Yes" if client.get('use_import_automation') else "No")
                    st.write("**Created:**", client['created_at'])

                if client.get('notes'):
                    st.write("**Notes:**", client['notes'])

                # Field mappings
                st.markdown("---")
                st.write("**Field Mappings:**")

                mappings = self.db.get_field_mappings(client['client_id'])
                if mappings:
                    mappings_df = pd.DataFrame(mappings)
                    st.dataframe(
                        mappings_df[['source_field', 'target_field', 'is_active']],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("No field mappings configured")

        else:
            st.warning("No clients found")

    def _render_add_client(self):
        """Render add client form."""
        st.subheader("Add New Client")

        with st.form("new_client"):
            col1, col2 = st.columns(2)

            with col1:
                client_name = st.text_input("Client Name *", placeholder="Acme Corp")
                client_code = st.text_input("Client Code *", placeholder="ACME")
                contact_name = st.text_input("Contact Name", placeholder="John Doe")

            with col2:
                contact_email = st.text_input("Contact Email", placeholder="john@acme.com")
                phone = st.text_input("Phone", placeholder="555-1234")

            col1, col2, col3 = st.columns(3)

            with col1:
                active = st.checkbox("Active", value=True)

            with col2:
                rpa_enabled = st.checkbox("RPA Enabled", value=False)

            with col3:
                use_import = st.checkbox("Import Automation", value=False)

            notes = st.text_area("Notes", placeholder="Additional notes...")

            submitted = st.form_submit_button("Create Client")

            if submitted:
                if not client_name or not client_code:
                    st.error("Client name and code are required")
                else:
                    try:
                        client_id = self.db.create_client(
                            client_name=client_name,
                            client_code=client_code.upper(),
                            contact_name=contact_name or None,
                            contact_email=contact_email or None,
                            phone=phone or None,
                            active=active,
                            rpa_enabled=rpa_enabled,
                            use_import_automation=use_import,
                            notes=notes or None
                        )
                        st.success(f"Client created successfully! (ID: {client_id})")
                    except Exception as e:
                        st.error(f"Error creating client: {str(e)}")

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    def render_analytics(self):
        """Render analytics dashboard."""
        st.header("📈 Analytics & Reporting")

        tab1, tab2, tab3 = st.tabs(["📊 Classification Metrics", "✅ Approval Metrics", "💰 Financial Summary"])

        with tab1:
            self._render_classification_analytics()

        with tab2:
            self._render_approval_analytics()

        with tab3:
            self._render_financial_analytics()

    def _render_classification_analytics(self):
        """Render classification analytics."""
        st.subheader("Classification Accuracy Metrics")

        data = self.db.get_classification_accuracy_report()

        if data:
            df = pd.DataFrame(data)
            df['classification_day'] = pd.to_datetime(df['classification_day'])

            # Line chart: Classifications over time
            fig = px.line(
                df,
                x='classification_day',
                y='total_classifications',
                color='source',
                title="Classifications Over Time (Last 30 Days)",
                labels={'classification_day': 'Date', 'total_classifications': 'Count'}
            )
            st.plotly_chart(fig, use_container_width=True)

            # Confidence chart
            fig2 = px.line(
                df,
                x='classification_day',
                y='avg_confidence',
                color='source',
                title="Average Confidence Score Over Time",
                labels={'classification_day': 'Date', 'avg_confidence': 'Avg Confidence'}
            )
            st.plotly_chart(fig2, use_container_width=True)

            # Summary table
            st.subheader("Summary by Source")
            summary = df.groupby('source').agg({
                'total_classifications': 'sum',
                'avg_confidence': 'mean',
                'high_confidence_count': 'sum',
                'low_confidence_count': 'sum'
            }).reset_index()

            st.dataframe(summary, use_container_width=True, hide_index=True)

        else:
            st.info("No classification metrics available")

    def _render_approval_analytics(self):
        """Render approval analytics."""
        st.subheader("Approval Workflow Metrics")

        data = self.db.get_approval_metrics()

        if data:
            df = pd.DataFrame(data)
            df['approval_day'] = pd.to_datetime(df['approval_day'])

            # Bar chart: Approvals by status
            fig = px.bar(
                df,
                x='approval_day',
                y='approval_count',
                color='approval_status',
                title="Approvals Over Time (Last 90 Days)",
                labels={'approval_day': 'Date', 'approval_count': 'Count'}
            )
            st.plotly_chart(fig, use_container_width=True)

            # Average approval time
            time_df = df[df['avg_approval_time_days'].notna()]
            if not time_df.empty:
                fig2 = px.line(
                    time_df,
                    x='approval_day',
                    y='avg_approval_time_days',
                    title="Average Approval Time (Days)",
                    labels={'approval_day': 'Date', 'avg_approval_time_days': 'Days'}
                )
                st.plotly_chart(fig2, use_container_width=True)

            # Summary
            st.subheader("Approval Summary")
            total_approvals = df['approval_count'].sum()
            rpa_ready = df['rpa_ready_count'].sum()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Approvals", f"{total_approvals:,}")

            with col2:
                st.metric("RPA Ready", f"{rpa_ready:,}")

            with col3:
                pct = (rpa_ready / total_approvals * 100) if total_approvals > 0 else 0
                st.metric("RPA Ready %", f"{pct:.1f}%")

        else:
            st.info("No approval metrics available")

    def _render_financial_analytics(self):
        """Render financial analytics."""
        st.subheader("Financial Summary")

        # Get export data
        exports = self.db.get_recent_exports(limit=100)

        if exports:
            df = pd.DataFrame(exports)
            df['export_date'] = pd.to_datetime(df['export_date'])

            # Filter by date range
            col1, col2 = st.columns(2)

            with col1:
                start_date = st.date_input(
                    "Start Date",
                    value=datetime.now() - timedelta(days=365)
                )

            with col2:
                end_date = st.date_input(
                    "End Date",
                    value=datetime.now()
                )

            # Filter data
            mask = (df['export_date'] >= pd.Timestamp(start_date)) & (df['export_date'] <= pd.Timestamp(end_date))
            filtered_df = df[mask]

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                total_cost = filtered_df['total_cost'].sum()
                st.metric("Total Asset Cost", f"${total_cost:,.0f}")

            with col2:
                total_179 = filtered_df.get('total_section_179', pd.Series([0])).sum()
                st.metric("Section 179", f"${total_179:,.0f}")

            with col3:
                total_bonus = filtered_df.get('total_bonus', pd.Series([0])).sum()
                st.metric("Bonus Depreciation", f"${total_bonus:,.0f}")

            with col4:
                total_deduction = filtered_df['year1_total_deduction'].sum()
                st.metric("Y1 Total Deduction", f"${total_deduction:,.0f}")

            # Chart: Cost over time
            if len(filtered_df) > 0:
                fig = px.bar(
                    filtered_df,
                    x='export_date',
                    y='total_cost',
                    title="Asset Cost by Export Date",
                    labels={'export_date': 'Date', 'total_cost': 'Total Cost'}
                )
                st.plotly_chart(fig, use_container_width=True)

                # Chart: Deduction breakdown
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    name='Section 179',
                    x=filtered_df['export_date'],
                    y=filtered_df.get('total_section_179', 0)
                ))
                fig2.add_trace(go.Bar(
                    name='Bonus',
                    x=filtered_df['export_date'],
                    y=filtered_df.get('total_bonus', 0)
                ))
                fig2.add_trace(go.Bar(
                    name='MACRS',
                    x=filtered_df['export_date'],
                    y=filtered_df.get('total_macrs_year1', 0)
                ))
                fig2.update_layout(
                    title="Y1 Deduction Breakdown",
                    barmode='stack',
                    xaxis_title="Date",
                    yaxis_title="Amount"
                )
                st.plotly_chart(fig2, use_container_width=True)

        else:
            st.info("No financial data available")


def render_management_ui():
    """Render management UI (main entry point)."""
    ui = ManagementUI()
    ui.render()
