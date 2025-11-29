import React from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

function Layout({ children, activeTab, setActiveTab }) {
    // Derive title from active tab
    const getTitle = () => {
        switch (activeTab) {
            case 'dashboard': return 'Dashboard';
            case 'import': return 'Import Asset Schedule';
            case 'review': return 'Review & Approve';
            case 'settings': return 'Settings';
            default: return 'FA CS Automator';
        }
    };

    return (
        <div className="flex h-screen bg-background overflow-hidden font-sans">
            <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
            <div className="flex-1 flex flex-col min-w-0">
                <Header title={getTitle()} />
                <main className="flex-1 overflow-auto p-6">
                    <div className="max-w-7xl mx-auto">
                        {children}
                    </div>
                </main>
            </div>
        </div>
    );
}

export { Layout };
export default Layout;
