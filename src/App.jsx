import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { Import } from './components/Import';
import { DataCleanup } from './components/DataCleanup';
import { Review } from './components/Review';
import { Settings } from './components/Settings';
import { apiGet } from './lib/api.client';

export default function App() {
    const [assets, setAssets] = useState([]);
    const navigate = useNavigate();

    // Fetch assets from backend session on mount (restores state after page refresh)
    useEffect(() => {
        const fetchAssets = async () => {
            try {
                const data = await apiGet('/assets');
                if (data && data.length > 0) {
                    setAssets(data);
                }
            } catch (error) {
                // Silent fail - no assets in session is normal for fresh sessions
                console.debug('No assets in session:', error);
            }
        };
        fetchAssets();
    }, []);

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