import React, { useState } from 'react';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './views/Dashboard';
import { Import } from './views/Import';
import { Review } from './views/Review';

export default function App() {
    const [activeTab, setActiveTab] = useState("dashboard");
    const [assets, setAssets] = useState([]);

    const handleUploadSuccess = (data) => {
        setAssets(data);
        setActiveTab("review");
    };

    const renderContent = () => {
        switch (activeTab) {
            case "dashboard": return <Dashboard />;
            case "import": return <Import onUploadSuccess={handleUploadSuccess} />;
            case "review": return <Review assets={assets} />;
            case "settings": return <div className="p-8">Settings (Coming Soon)</div>;
            default: return <Dashboard />;
        }
    };

    return (
        <Layout activeTab={activeTab} setActiveTab={setActiveTab}>
            {renderContent()}
        </Layout>
    );
}