import React, { useState } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { Import } from './components/Import';
import { DataCleanup } from './components/DataCleanup';
import { Review } from './components/Review';
import { Settings } from './components/Settings';

export default function App() {
    const [assets, setAssets] = useState([]);
    const navigate = useNavigate();

    const handleUploadSuccess = (data) => {
        setAssets(data);
        navigate('/cleanup');  // Go to Data Cleanup first before Review
    };

    return (
        <Layout>
            <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/import" element={<Import onUploadSuccess={handleUploadSuccess} />} />
                <Route path="/cleanup" element={<DataCleanup />} />
                <Route path="/review" element={<Review assets={assets} />} />
                <Route path="/review/:sessionId" element={<Review assets={assets} />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
        </Layout>
    );
}