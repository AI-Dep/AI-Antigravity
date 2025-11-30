import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Info, Calendar, DollarSign } from 'lucide-react';
import axios from 'axios';

function Settings() {
    const [config, setConfig] = useState({
        tax_year: new Date().getFullYear(),
        de_minimis_threshold: 2500,
        has_afs: false,
        bonus_rate: null,
        section_179_limit: null,
        obbba_effective: false,
        obbba_info: null
    });
    const [warnings, setWarnings] = useState({ critical: [], warnings: [], info: [] });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        fetchConfig();
        fetchWarnings();
    }, []);

    const fetchConfig = async () => {
        try {
            const response = await axios.get('http://127.0.0.1:8000/config/tax');
            setConfig(response.data);
        } catch (error) {
            console.error('Failed to fetch config:', error);
        } finally {
            setLoading(false);
        }
    };

    const fetchWarnings = async () => {
        try {
            const response = await axios.get('http://127.0.0.1:8000/warnings');
            setWarnings(response.data);
        } catch (error) {
            console.error('Failed to fetch warnings:', error);
        }
    };

    const saveConfig = async () => {
        setSaving(true);
        try {
            const response = await axios.post('http://127.0.0.1:8000/config/tax', {
                tax_year: config.tax_year,
                de_minimis_threshold: config.de_minimis_threshold,
                has_afs: config.has_afs
            });

            // Refresh config and warnings after save
            await fetchConfig();
            await fetchWarnings();

            alert(`Configuration saved! ${response.data.assets_reclassified} assets reclassified.`);
        } catch (error) {
            console.error('Failed to save config:', error);
            alert('Failed to save configuration');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="p-8 flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    return (
        <div className="p-8 max-w-4xl mx-auto space-y-6">
            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                    Tax Configuration
                </h1>
                <p className="text-slate-500 dark:text-slate-400 mt-2">
                    Configure tax year and depreciation settings for proper asset classification.
                </p>
            </div>

            {/* Warnings Section */}
            {warnings.critical?.length > 0 && (
                <Card className="border-red-200 bg-red-50">
                    <CardHeader>
                        <CardTitle className="text-red-800 flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5" />
                            Critical Warnings ({warnings.critical.length})
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {warnings.critical.map((warning, idx) => (
                            <div key={idx} className="mb-4 p-3 bg-white rounded border border-red-200">
                                <div className="font-semibold text-red-800">{warning.message}</div>
                                <div className="text-sm text-red-600 mt-1">{warning.impact}</div>
                                <div className="text-sm text-slate-600 mt-1">
                                    <strong>Action:</strong> {warning.action}
                                </div>
                            </div>
                        ))}
                    </CardContent>
                </Card>
            )}

            {/* Tax Year Configuration */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Calendar className="w-5 h-5 text-blue-600" />
                        Tax Year Settings
                    </CardTitle>
                    <CardDescription>
                        Set the tax year for transaction classification and depreciation calculations.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-2">
                            Tax Year
                        </label>
                        <select
                            value={config.tax_year}
                            onChange={(e) => setConfig({ ...config, tax_year: parseInt(e.target.value) })}
                            className="w-full border rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-blue-500"
                        >
                            {[2020, 2021, 2022, 2023, 2024, 2025, 2026].map(year => (
                                <option key={year} value={year}>{year}</option>
                            ))}
                        </select>
                        <p className="text-xs text-slate-500 mt-1">
                            Assets placed in service in this year are classified as "Current Year Additions"
                        </p>
                    </div>

                    {/* OBBBA 2025 Info */}
                    {config.tax_year >= 2025 && (
                        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                            <div className="flex items-center gap-2 text-blue-800 font-semibold">
                                <Info className="w-4 h-4" />
                                OBBBA 2025 Provisions Apply
                            </div>
                            <ul className="text-sm text-blue-700 mt-2 space-y-1">
                                <li>- Bonus Depreciation: 100% for assets acquired & placed in service after 1/19/2025</li>
                                <li>- Section 179 Limit: $2.5 million (increased from $1.2M)</li>
                                <li>- Phase-out Threshold: $4 million</li>
                            </ul>
                        </div>
                    )}

                    {/* Bonus Rate Display */}
                    <div className="grid grid-cols-2 gap-4 p-4 bg-slate-50 rounded-lg">
                        <div>
                            <div className="text-sm text-slate-500">Bonus Depreciation Rate</div>
                            <div className="text-2xl font-bold text-slate-900">
                                {config.bonus_rate}%
                            </div>
                        </div>
                        <div>
                            <div className="text-sm text-slate-500">Section 179 Limit</div>
                            <div className="text-2xl font-bold text-slate-900">
                                ${config.section_179_limit?.toLocaleString()}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* De Minimis Configuration */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <DollarSign className="w-5 h-5 text-green-600" />
                        De Minimis Safe Harbor
                    </CardTitle>
                    <CardDescription>
                        Configure the de minimis expensing threshold (IRC Reg. 1.263(a)-1(f))
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-2">
                            De Minimis Threshold
                        </label>
                        <select
                            value={config.de_minimis_threshold}
                            onChange={(e) => setConfig({
                                ...config,
                                de_minimis_threshold: parseInt(e.target.value),
                                has_afs: parseInt(e.target.value) === 5000
                            })}
                            className="w-full border rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-blue-500"
                        >
                            <option value={0}>Disabled ($0)</option>
                            <option value={2500}>$2,500 (Without Audited Financial Statements)</option>
                            <option value={5000}>$5,000 (With Audited Financial Statements)</option>
                        </select>
                        <p className="text-xs text-slate-500 mt-1">
                            Items below this threshold can be expensed immediately instead of depreciated.
                        </p>
                    </div>

                    <div className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            id="has_afs"
                            checked={config.has_afs}
                            onChange={(e) => setConfig({
                                ...config,
                                has_afs: e.target.checked,
                                de_minimis_threshold: e.target.checked ? 5000 : 2500
                            })}
                            className="w-4 h-4 rounded border-slate-300"
                        />
                        <label htmlFor="has_afs" className="text-sm text-slate-700">
                            Taxpayer has Audited Financial Statements (AFS)
                        </label>
                    </div>
                </CardContent>
            </Card>

            {/* Regular Warnings */}
            {warnings.warnings?.length > 0 && (
                <Card className="border-yellow-200 bg-yellow-50">
                    <CardHeader>
                        <CardTitle className="text-yellow-800 flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5" />
                            Warnings ({warnings.warnings.length})
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {warnings.warnings.map((warning, idx) => (
                            <div key={idx} className="mb-3 p-3 bg-white rounded border border-yellow-200">
                                <div className="font-medium text-yellow-800">{warning.message}</div>
                                <div className="text-sm text-slate-600 mt-1">{warning.action}</div>
                            </div>
                        ))}
                    </CardContent>
                </Card>
            )}

            {/* Save Button */}
            <div className="flex justify-end">
                <Button
                    onClick={saveConfig}
                    disabled={saving}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-6"
                >
                    {saving ? 'Saving...' : 'Save Configuration'}
                </Button>
            </div>
        </div>
    );
}

export { Settings };
export default Settings;
