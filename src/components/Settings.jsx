import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Info, Calendar, DollarSign, Hash } from 'lucide-react';
import { apiGet, apiPost } from '../lib/api.client';

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
    const [facsConfig, setFacsConfig] = useState({
        asset_number_start: 1,
        remote_mode: true,
    });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        fetchConfig();
        fetchFacsConfig();
    }, []);

    const fetchConfig = async () => {
        try {
            const data = await apiGet('/config/tax');
            setConfig(data);
        } catch (error) {
            console.error('Failed to fetch config:', error);
        } finally {
            setLoading(false);
        }
    };

    const fetchFacsConfig = async () => {
        try {
            const data = await apiGet('/facs/config');
            setFacsConfig(prev => ({
                ...prev,
                asset_number_start: data.asset_number_start || 1,
                remote_mode: data.remote_mode ?? true,
            }));
        } catch (error) {
            console.error('Failed to fetch FA CS config:', error);
        }
    };

    const saveFacsConfig = async () => {
        try {
            await apiPost('/facs/config', {
                asset_number_start: facsConfig.asset_number_start,
                remote_mode: facsConfig.remote_mode,
            });
            return true;
        } catch (error) {
            console.error('Failed to save FA CS config:', error);
            return false;
        }
    };

    const saveConfig = async () => {
        setSaving(true);
        try {
            // Save tax config
            const data = await apiPost('/config/tax', {
                tax_year: config.tax_year,
                de_minimis_threshold: config.de_minimis_threshold,
                has_afs: config.has_afs
            });

            // Save FA CS config
            await saveFacsConfig();

            // Refresh config after save
            await fetchConfig();
            await fetchFacsConfig();

            alert(`Configuration saved! ${data.assets_reclassified} assets reclassified.`);
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

            {/* FA CS Asset Numbering */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Hash className="w-5 h-5 text-purple-600" />
                        FA CS Asset Numbering
                    </CardTitle>
                    <CardDescription>
                        Configure how FA CS Asset #s are assigned for new assets.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-2">
                            Starting Asset Number
                        </label>
                        <input
                            type="number"
                            min="1"
                            value={facsConfig.asset_number_start}
                            onChange={(e) => setFacsConfig({
                                ...facsConfig,
                                asset_number_start: Math.max(1, parseInt(e.target.value) || 1)
                            })}
                            className="w-full border rounded-lg px-3 py-2 text-slate-900 focus:ring-2 focus:ring-blue-500"
                        />
                        <p className="text-xs text-slate-500 mt-1">
                            If your client already has assets in FA CS (e.g., 1000 existing assets),
                            set this to the next available number (e.g., 1001) to avoid collisions.
                        </p>
                    </div>

                    <div className="p-4 bg-purple-50 border border-purple-200 rounded-lg">
                        <div className="flex items-center gap-2 text-purple-800 font-semibold text-sm">
                            <Info className="w-4 h-4" />
                            How Asset Numbers Work
                        </div>
                        <ul className="text-xs text-purple-700 mt-2 space-y-1">
                            <li>• New additions will be assigned numbers starting from {facsConfig.asset_number_start}</li>
                            <li>• Existing assets keep their original FA CS numbers if imported</li>
                            <li>• You can manually edit individual Asset #s in the Review table</li>
                        </ul>
                    </div>
                </CardContent>
            </Card>

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
