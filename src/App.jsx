import React, { useState } from 'react';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { Import } from './components/Import';
import { DataCleanup } from './components/DataCleanup';
import { Review } from './components/Review';
import { Settings } from './components/Settings';

export default function App() {
    const [activeTab, setActiveTab] = useState("dashboard");
    const [assets, setAssets] = useState([]);

    const handleUploadSuccess = (data) => {
        setAssets(data);
        setActiveTab("cleanup");  // Go to Data Cleanup first before Review
    };

    const renderContent = () => {
        switch (activeTab) {
            case "dashboard": return <Dashboard setActiveTab={setActiveTab} />;
            case "import": return <Import onUploadSuccess={handleUploadSuccess} />;
            case "cleanup": return <DataCleanup setActiveTab={setActiveTab} />;
            case "review": return <Review assets={assets} />;
            case "settings": return <Settings />;
            default: return <Dashboard />;
        }
    };

    return (
        <Layout activeTab={activeTab} setActiveTab={setActiveTab}>
            {renderContent()}
        </Layout>
    );
}