import React from 'react';
import { useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

// Map route paths to page titles
const routeTitles = {
    '/dashboard': 'Dashboard',
    '/import': 'Import Asset Schedule',
    '/cleanup': 'Data Cleanup',
    '/review': 'Review & Approve',
    '/settings': 'Settings',
};

function Layout({ children }) {
    const location = useLocation();

    // Derive title from current route
    const getTitle = () => {
        // Handle parameterized routes like /review/:sessionId
        const basePath = '/' + location.pathname.split('/')[1];
        return routeTitles[basePath] || 'FA CS Automator';
    };

    return (
        <div className="flex h-screen bg-background overflow-hidden font-sans">
            <Sidebar />
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
