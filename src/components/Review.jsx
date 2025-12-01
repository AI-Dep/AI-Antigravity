import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Check, X, AlertTriangle, Edit2, Save, CheckCircle, Download, Info, Eye, EyeOff, FileText, Loader2, Shield, Wand2, DollarSign, Calculator } from 'lucide-react';
import { cn } from '../lib/utils';

// Import API types for consistent contract
import { TRANSACTION_TYPES } from '../lib/api.types';

// Import centralized API client
import { apiGet, apiPost, apiDownload } from '../lib/api.client';

function Review({ assets = [] }) {
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const [localAssets, setLocalAssets] = useState(assets);
    const [filter, setFilter] = useState('all'); // all, errors, review, approved
    const [showExistingAssets, setShowExistingAssets] = useState(false); // Hide existing by default
    const [approvedIds, setApprovedIds] = useState(new Set());
    const [warnings, setWarnings] = useState({ critical: [], warnings: [], info: [], summary: {} });
    const [taxYear, setTaxYear] = useState(new Date().getFullYear());
    const [taxYearLoading, setTaxYearLoading] = useState(false); // Loading state for tax year change
    const [tableCompact, setTableCompact] = useState(false); // Table density: false = comfortable, true = compact
    const [exportStatus, setExportStatus] = useState({ ready: false, reason: null }); // Track export readiness
    const [compatibilityCheck, setCompatibilityCheck] = useState(null); // FA CS compatibility check results
    const [showCompatDialog, setShowCompatDialog] = useState(false); // Show compatibility dialog
    const [depreciationPreview, setDepreciationPreview] = useState(null); // 179/Bonus preview
    const [checkingCompatibility, setCheckingCompatibility] = useState(false);

    // Fetch warnings and export status when assets change
    useEffect(() => {
        if (assets.length > 0) {
            fetchWarnings();
            fetchTaxConfig();
            fetchExportStatus();
        }
    }, [assets]);

    // Fetch export status whenever approvals change
    // NOTE: Only fetch status, don't sync approvedIds here to avoid infinite loop
    useEffect(() => {
        if (localAssets.length > 0) {
            fetchExportStatusOnly();
        }
    }, [approvedIds]);

    const fetchWarnings = async () => {
        try {
            const data = await apiGet('/warnings');
            setWarnings(data);
        } catch (error) {
            console.error('Failed to fetch warnings:', error);
        }
    };

    const fetchTaxConfig = async () => {
        try {
            const data = await apiGet('/config/tax');
            setTaxYear(data.tax_year);
        } catch (error) {
            console.error('Failed to fetch tax config:', error);
        }
    };

    // Fetch export status only (without syncing approvedIds) - used by approvedIds useEffect
    const fetchExportStatusOnly = async () => {
        try {
            const data = await apiGet('/export/status');
            setExportStatus(data);
            // Don't sync approvedIds here - it would cause infinite loop
        } catch (error) {
            console.error('Failed to fetch export status:', error);
        }
    };

    // Fetch export status AND sync approvedIds from backend - used on initial load
    const fetchExportStatus = async () => {
        try {
            const data = await apiGet('/export/status');
            setExportStatus(data);
            // Sync approved IDs from backend on initial load
            if (data.approved_ids) {
                setApprovedIds(new Set(data.approved_ids));
            }
        } catch (error) {
            console.error('Failed to fetch export status:', error);
        }
    };

    // Check FA CS compatibility before export
    const checkFACSCompatibility = async () => {
        setCheckingCompatibility(true);
        try {
            const data = await apiGet('/export/compatibility-check');
            setCompatibilityCheck(data);
            setShowCompatDialog(true);

            // Also fetch depreciation preview
            const preview = await apiGet('/export/depreciation-preview');
            setDepreciationPreview(preview);
        } catch (error) {
            console.error('Failed to check compatibility:', error);
            // Show dialog anyway with error state
            setCompatibilityCheck({ error: error.message });
            setShowCompatDialog(true);
        } finally {
            setCheckingCompatibility(false);
        }
    };

    // Auto-fix compatibility issues
    const autoFixCompatibilityIssues = async () => {
        try {
            const result = await apiPost('/export/auto-fix');
            // Re-check compatibility after fix
            await checkFACSCompatibility();
            // Refresh assets
            const assetsData = await apiGet('/assets');
            if (assetsData && Array.isArray(assetsData)) {
                setLocalAssets(assetsData);
            }
        } catch (error) {
            console.error('Failed to auto-fix:', error);
        }
    };

    const handleTaxYearChange = async (e) => {
        const newYear = parseInt(e.target.value, 10);
        setTaxYearLoading(true);
        try {
            const data = await apiPost('/config/tax', {
                tax_year: newYear
            });
            setTaxYear(newYear);

            // Update local assets with reclassified data from the backend
            if (data.assets && Array.isArray(data.assets)) {
                if (data.assets.length > 0) {
                    // Backend returned reclassified assets - use them
                    setLocalAssets(data.assets);
                    setApprovedIds(new Set()); // Clear approvals on reclassification
                } else {
                    // Backend returned empty array - fetch fresh assets
                    console.warn('Tax year change returned no assets, fetching from server...');
                    const assetsData = await apiGet('/assets');
                    if (assetsData && assetsData.length > 0) {
                        setLocalAssets(assetsData);
                        setApprovedIds(new Set());
                    }
                }
            }
            // Refresh warnings and export status for new tax year
            fetchWarnings();
            fetchExportStatus();
        } catch (error) {
            console.error('Failed to update tax year:', error);
        } finally {
            setTaxYearLoading(false);
        }
    };

    // Sync local assets when props change
    useEffect(() => {
        setLocalAssets(assets);
        setApprovedIds(new Set());
    }, [assets]);

    // Calculate stats
    const stats = useMemo(() => {
        const errors = localAssets.filter(a => a.validation_errors?.length > 0).length;
        const needsReview = localAssets.filter(a =>
            !a.validation_errors?.length && a.confidence_score <= 0.8
        ).length;
        const highConfidence = localAssets.filter(a =>
            !a.validation_errors?.length && a.confidence_score > 0.8
        ).length;
        const approved = approvedIds.size;
        const totalCost = localAssets.reduce((sum, a) => sum + (a.cost || 0), 0);

        // Count by transaction type
        const allAdditions = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.ADDITION
        );
        const additions = allAdditions.length;

        // De Minimis items (expensed, not capitalized)
        const deMinimisItems = allAdditions.filter(a =>
            a.depreciation_election === 'DeMinimis'
        );
        const deMinimisCount = deMinimisItems.length;
        const deMinimisTotal = deMinimisItems.reduce((sum, a) => sum + (a.cost || 0), 0);
        const capitalAdditions = additions - deMinimisCount;

        const disposals = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.DISPOSAL
        ).length;
        const transfers = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.TRANSFER
        ).length;
        const existing = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.EXISTING
        ).length;
        const actionable = additions + disposals + transfers;

        return {
            total: localAssets.length,
            errors,
            needsReview,
            highConfidence,
            approved,
            totalCost,
            additions,
            capitalAdditions,
            deMinimisCount,
            deMinimisTotal,
            disposals,
            transfers,
            existing,
            actionable
        };
    }, [localAssets, approvedIds]);

    // Filter assets
    const filteredAssets = useMemo(() => {
        // First apply the showExistingAssets filter
        let baseAssets = localAssets;
        if (!showExistingAssets) {
            // Hide existing assets - only show actionable items (additions, disposals, transfers)
            baseAssets = localAssets.filter(a =>
                a.transaction_type !== TRANSACTION_TYPES.EXISTING
            );
        }

        // Then apply the status filter
        switch (filter) {
            case 'errors':
                return baseAssets.filter(a => a.validation_errors?.length > 0);
            case 'review':
                return baseAssets.filter(a =>
                    !a.validation_errors?.length && a.confidence_score <= 0.8
                );
            case 'approved':
                // Use unique_id for approval tracking (unique across sheets)
                return baseAssets.filter(a => approvedIds.has(a.unique_id));
            default:
                return baseAssets;
        }
    }, [localAssets, filter, approvedIds, showExistingAssets]);

    // Check if export should be disabled
    const hasBlockingErrors = stats.errors > 0;
    const allReviewed = stats.needsReview === 0 ||
        localAssets.filter(a => !a.validation_errors?.length && a.confidence_score <= 0.8)
            .every(a => approvedIds.has(a.unique_id));

    // FA CS Wizard dropdown options by recovery period
    // Must match exact text from FA CS Add Asset Wizard for RPA compatibility
    const FA_CS_WIZARD_OPTIONS = {
        0: [
            "Land (non-depreciable)",
        ],
        5: [
            "Computer, monitor, laptop, PDA, other computer related, property used in research",
            "Automobile - passenger (used over 50% for business)",
            "Light truck or van (actual weight under 13,000 lbs)",
            "Appliance - large (refrigerator, stove, washer, dryer, etc.)",
            "Calculator, copier, fax, noncomputer office machine, typewriter",
        ],
        7: [
            "Furniture and fixtures - office",
            "Machinery and equipment - manufacturing",
        ],
        15: [
            "Land improvement (sidewalk, road, bridge, fence, landscaping)",
            "Qualified improvement property (QIP) - 15 year",
            "Intangible asset - Section 197 (15 year amortization)",
        ],
        27.5: [
            "Residential rental property (27.5 year)",
        ],
        39: [
            "Nonresidential real property (39 year)",
        ],
    };

    const handleEditClick = (asset) => {
        // Use unique_id for tracking edit state (unique across sheets)
        setEditingId(asset.unique_id);
        setEditForm({
            macrs_class: asset.macrs_class,
            macrs_life: asset.macrs_life,
            macrs_method: asset.macrs_method,
            fa_cs_wizard_category: asset.fa_cs_wizard_category
        });
    };

    const handleSave = async (uniqueId) => {
        try {
            // Include fa_cs_wizard_category in the update
            const updateData = {
                ...editForm,
                fa_cs_wizard_category: editForm.fa_cs_wizard_category
            };
            // Use unique_id for matching assets (unique across sheets)
            const updatedAssets = localAssets.map(a =>
                a.unique_id === uniqueId ? { ...a, ...updateData, confidence_score: 1.0 } : a
            );
            setLocalAssets(updatedAssets);
            setEditingId(null);

            // Update backend first
            await apiPost(`/assets/${uniqueId}/update`, updateData);

            // Then approve the asset (editing = implicit review/approval)
            await apiPost(`/assets/${uniqueId}/approve`);
            setApprovedIds(prev => new Set([...prev, uniqueId]));
        } catch (error) {
            console.error("Failed to save update:", error);
        }
    };

    const handleElectionChange = async (uniqueId, newElection) => {
        try {
            // Update local state immediately for responsive UI
            setLocalAssets(prev => prev.map(a =>
                a.unique_id === uniqueId
                    ? { ...a, depreciation_election: newElection }
                    : a
            ));
            // Call backend to persist the election change
            await apiPost(`/assets/${uniqueId}/election`, { election: newElection });
        } catch (error) {
            console.error("Failed to update election:", error);
        }
    };

    // Generic asset field update (for FA CS #, etc.)
    const handleAssetUpdate = async (uniqueId, updateData) => {
        try {
            // Update local state immediately for responsive UI
            setLocalAssets(prev => prev.map(a =>
                a.unique_id === uniqueId
                    ? { ...a, ...updateData }
                    : a
            ));
            // Call backend to persist the update
            await apiPost(`/assets/${uniqueId}/update`, updateData);
        } catch (error) {
            console.error("Failed to update asset:", error);
        }
    };

    const handleApprove = async (uniqueId) => {
        try {
            // Call backend to record approval
            await apiPost(`/assets/${uniqueId}/approve`);
            setApprovedIds(prev => new Set([...prev, uniqueId]));
        } catch (error) {
            console.error("Failed to approve asset:", error);
            alert(`Failed to approve: ${error.message || 'Unknown error'}`);
        }
    };

    const handleApproveAllHighConfidence = async () => {
        try {
            // Get all high confidence asset IDs
            const highConfIds = localAssets
                .filter(a => !a.validation_errors?.length && a.confidence_score > 0.8)
                .map(a => a.unique_id);

            if (highConfIds.length === 0) return;

            // Batch approve on backend
            await apiPost('/assets/approve-batch', highConfIds);
            setApprovedIds(prev => new Set([...prev, ...highConfIds]));
        } catch (error) {
            console.error("Failed to approve batch:", error);
            alert(`Failed to approve: ${error.message || 'Unknown error'}`);
        }
    };

    // Helper function to download file without opening new window (works in Electron)
    const downloadFile = async (endpoint, defaultFilename) => {
        try {
            const blob = await apiDownload(endpoint);

            // Trigger browser download
            const blobUrl = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = defaultFilename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (error) {
            alert(`Export blocked: ${error.message || 'Unknown error'}`);
        }
    };

    const handleExport = () => {
        // Double-check export readiness before attempting
        if (!exportStatus.ready) {
            alert(`Cannot export: ${exportStatus.reason || 'Not all assets are approved'}`);
            return;
        }
        downloadFile('/export', 'FA_CS_Import.xlsx');
    };

    const handleAuditReport = () => {
        downloadFile('/export/audit', 'Audit_Report.xlsx');
    };

    if (!localAssets || localAssets.length === 0) {
        return (
            <div className="p-8 text-center">
                <h2 className="text-xl font-semibold text-slate-700">No assets to review</h2>
                <p className="text-slate-500">Import a file first to see results here.</p>
            </div>
        );
    }

    return (
        <div className="p-6 max-w-[1900px] mx-auto">
            {/* Header */}
            <div className="flex justify-between items-start mb-6">
                <div>
                    <div className="flex items-center gap-3">
                        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                            Review & Approve
                        </h1>
                        <div className="relative inline-block">
                            <select
                                value={taxYear}
                                onChange={handleTaxYearChange}
                                disabled={taxYearLoading}
                                className={cn(
                                    "px-3 py-1 text-sm font-semibold bg-blue-100 text-blue-800 rounded-full border border-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-400 appearance-none pr-8",
                                    taxYearLoading ? "opacity-50 cursor-wait" : "cursor-pointer hover:bg-blue-200"
                                )}
                            >
                                {[2020, 2021, 2022, 2023, 2024, 2025, 2026].map(year => (
                                    <option key={year} value={year}>Tax Year {year}</option>
                                ))}
                            </select>
                            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2 text-blue-800">
                                {taxYearLoading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                    </svg>
                                )}
                            </div>
                        </div>
                    </div>
                    <p className="text-slate-500 dark:text-slate-400 mt-2">
                        Review AI classifications before export. Low confidence items need your attention.
                    </p>
                </div>
                <div className="flex gap-3">
                    <Button
                        variant="outline"
                        onClick={handleApproveAllHighConfidence}
                        className="text-green-600 hover:bg-green-50"
                    >
                        <CheckCircle className="w-4 h-4 mr-2" />
                        Approve All High Confidence
                    </Button>
                    <Button
                        variant="outline"
                        onClick={handleAuditReport}
                        className="text-slate-600 hover:bg-slate-50"
                        title="Download full asset schedule for audit documentation"
                    >
                        <FileText className="w-4 h-4 mr-2" />
                        Audit Report
                    </Button>
                    <Button
                        onClick={checkFACSCompatibility}
                        disabled={!exportStatus.ready || checkingCompatibility}
                        title={exportStatus.ready ? "Check FA CS compatibility and export" : exportStatus.reason || "Not ready to export"}
                        className={cn(
                            "text-white",
                            !exportStatus.ready
                                ? "bg-gray-400 cursor-not-allowed"
                                : "bg-green-600 hover:bg-green-700"
                        )}
                    >
                        {checkingCompatibility ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <Shield className="w-4 h-4 mr-2" />
                        )}
                        Export to FA CS
                    </Button>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-5 gap-4 mb-6">
                <div
                    onClick={() => setFilter('all')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'all' ? "border-blue-500 bg-blue-50" : "border-slate-200 hover:border-slate-300"
                    )}
                >
                    <div className="text-2xl font-bold text-slate-900">{stats.total}</div>
                    <div className="text-sm text-slate-500">Total Assets</div>
                    <div className="text-xs text-slate-400 mt-1">${stats.totalCost.toLocaleString()}</div>
                </div>
                <div
                    onClick={() => setFilter('errors')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'errors' ? "border-red-500 bg-red-50" : "border-slate-200 hover:border-slate-300",
                        stats.errors > 0 && "border-red-200 bg-red-50"
                    )}
                >
                    <div className={cn("text-2xl font-bold", stats.errors > 0 ? "text-red-600" : "text-slate-900")}>
                        {stats.errors}
                    </div>
                    <div className="text-sm text-slate-500">Errors</div>
                    <div className="text-xs text-red-500 mt-1">{stats.errors > 0 ? "Must fix before export" : "None"}</div>
                </div>
                <div
                    onClick={() => setFilter('review')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'review' ? "border-yellow-500 bg-yellow-50" : "border-slate-200 hover:border-slate-300"
                    )}
                >
                    <div className="text-2xl font-bold text-yellow-600">{stats.needsReview}</div>
                    <div className="text-sm text-slate-500">Needs Review</div>
                    <div className="text-xs text-slate-400 mt-1">Low confidence</div>
                </div>
                <div
                    className="p-4 rounded-lg border border-slate-200 cursor-default"
                >
                    <div className="text-2xl font-bold text-green-600">{stats.highConfidence}</div>
                    <div className="text-sm text-slate-500">High Confidence</div>
                    <div className="text-xs text-slate-400 mt-1">&gt;80% confidence</div>
                </div>
                <div
                    onClick={() => setFilter('approved')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'approved' ? "border-green-500 bg-green-50" : "border-slate-200 hover:border-slate-300"
                    )}
                >
                    <div className="text-2xl font-bold text-green-600">{stats.approved}</div>
                    <div className="text-sm text-slate-500">Approved</div>
                    <div className="text-xs text-slate-400 mt-1">Ready to export</div>
                </div>
            </div>

            {/* Critical Warnings Banner */}
            {warnings.critical?.length > 0 && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <div className="flex items-center gap-2 text-red-800 font-semibold mb-2">
                        <AlertTriangle className="w-5 h-5" />
                        Critical Compliance Warnings ({warnings.critical.length})
                    </div>
                    {warnings.critical.slice(0, 2).map((warning, idx) => (
                        <div key={idx} className="text-sm text-red-700 mb-1">
                            <strong>{warning.type}:</strong> {warning.message}
                            <span className="text-red-600 ml-2">({warning.affected_count} assets)</span>
                        </div>
                    ))}
                    <div className="text-xs text-red-600 mt-2">
                        Go to Settings to configure tax year and resolve warnings.
                    </div>
                </div>
            )}

            {/* Error Banner */}
            {hasBlockingErrors && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                    <div>
                        <div className="font-medium text-red-800">
                            {stats.errors} asset(s) have validation errors
                        </div>
                        <div className="text-sm text-red-600">
                            Fix all errors before exporting to Fixed Asset CS
                        </div>
                    </div>
                </div>
            )}

            {/* View Toggle - Actionable vs All Assets */}
            <div className="mb-4 p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-700">View:</span>
                        <button
                            onClick={() => setShowExistingAssets(false)}
                            className={cn(
                                "px-3 py-1.5 rounded-lg text-sm font-medium transition-all",
                                !showExistingAssets
                                    ? "bg-blue-600 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            Actionable Only ({stats.actionable})
                        </button>
                        <button
                            onClick={() => setShowExistingAssets(true)}
                            className={cn(
                                "px-3 py-1.5 rounded-lg text-sm font-medium transition-all",
                                showExistingAssets
                                    ? "bg-blue-600 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            All Assets ({stats.total})
                        </button>
                    </div>
                    <div className="h-6 w-px bg-slate-300" />
                    <div className="flex items-center gap-3 text-xs text-slate-500">
                        <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded">
                            {stats.capitalAdditions} Additions
                        </span>
                        {stats.deMinimisCount > 0 && (
                            <span
                                className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded cursor-help"
                                title={`$${stats.deMinimisTotal.toLocaleString()} expensed via De Minimis Safe Harbor - NOT added to FA CS`}
                            >
                                {stats.deMinimisCount} Expensed
                            </span>
                        )}
                        <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded">
                            {stats.disposals} Disposals
                        </span>
                        <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                            {stats.transfers} Transfers
                        </span>
                        {showExistingAssets && (
                            <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                                {stats.existing} Existing
                            </span>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    {/* Table Density Toggle */}
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500">Density:</span>
                        <button
                            onClick={() => setTableCompact(false)}
                            className={cn(
                                "px-2 py-1 rounded text-xs font-medium transition-all",
                                !tableCompact
                                    ? "bg-slate-700 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            Comfortable
                        </button>
                        <button
                            onClick={() => setTableCompact(true)}
                            className={cn(
                                "px-2 py-1 rounded text-xs font-medium transition-all",
                                tableCompact
                                    ? "bg-slate-700 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            Compact
                        </button>
                    </div>
                    {!showExistingAssets && stats.existing > 0 && (
                        <div className="text-xs text-slate-500 flex items-center gap-1">
                            <EyeOff className="w-3 h-3" />
                            {stats.existing} existing assets hidden (no action required)
                        </div>
                    )}
                </div>
            </div>

            {/* Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className={cn(
                            "w-full text-left min-w-[1200px]",
                            tableCompact ? "text-xs" : "text-sm"
                        )} style={{ tableLayout: 'fixed' }}>
                            <thead className={cn(
                                "text-xs text-slate-500 uppercase bg-slate-50 dark:bg-slate-900/50 border-b",
                                tableCompact ? "text-[10px]" : "text-xs"
                            )}>
                                <tr>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '90px', minWidth: '70px', resize: 'horizontal', overflow: 'hidden' }}>Status</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '55px', minWidth: '45px', resize: 'horizontal', overflow: 'hidden' }}>Conf.</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '80px', minWidth: '60px', resize: 'horizontal', overflow: 'hidden' }}>Asset ID</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '70px', minWidth: '55px', resize: 'horizontal', overflow: 'hidden' }}>
                                        <span className="flex items-center gap-1 cursor-help" title="FA CS Asset # (numeric). Edit to resolve collisions with client Asset IDs.">
                                            FA CS #
                                            <Info className="w-3 h-3 text-slate-400" />
                                        </span>
                                    </th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '220px', minWidth: '120px', resize: 'horizontal', overflow: 'hidden' }}>Description</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '100px', minWidth: '70px', resize: 'horizontal', overflow: 'hidden' }}>Cost</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '110px', minWidth: '90px', resize: 'horizontal', overflow: 'hidden' }}>
                                        <span className="flex items-center gap-1 cursor-help" title="Additions/Existing: Date In Service | Disposals: Disposal Date | Transfers: Transfer Date">
                                            Key Date
                                            <Info className="w-3 h-3 text-slate-400" />
                                        </span>
                                    </th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '100px', minWidth: '70px', resize: 'horizontal', overflow: 'hidden' }}>Trans. Type</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '100px', minWidth: '60px', resize: 'horizontal', overflow: 'hidden' }}>Class</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '60px', minWidth: '45px', resize: 'horizontal', overflow: 'hidden' }}>Life</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '70px', minWidth: '55px', resize: 'horizontal', overflow: 'hidden' }}>Method</th>
                                    <th className={cn("resizable-col", tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '100px', minWidth: '80px', resize: 'horizontal', overflow: 'hidden' }}>
                                        <span className="flex items-center gap-1">
                                            Election
                                            <span className="text-[9px] bg-blue-100 text-blue-700 px-1 rounded">179/Bonus</span>
                                        </span>
                                    </th>
                                    <th className={cn(tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '80px', minWidth: '60px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredAssets.map((asset) => {
                                    // Use unique_id for approval tracking (unique across sheets)
                                    const isApproved = approvedIds.has(asset.unique_id);
                                    const hasErrors = asset.validation_errors?.length > 0;
                                    const needsReview = !hasErrors && asset.confidence_score <= 0.8;
                                    const isDeMinimis = asset.depreciation_election === 'DeMinimis';

                                    return (
                                        <tr
                                            key={asset.unique_id}
                                            className={cn(
                                                "border-b hover:bg-slate-50 dark:border-slate-800",
                                                hasErrors && "bg-red-50/50",
                                                needsReview && !isApproved && "bg-yellow-50/30",
                                                isApproved && "bg-green-50/30",
                                                isDeMinimis && "bg-emerald-50/40 opacity-75"
                                            )}
                                        >
                                            {/* Status - MOVED TO FIRST COLUMN */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                {hasErrors ? (
                                                    <div className="group relative flex items-center">
                                                        <span className={cn(
                                                            "inline-flex items-center rounded-full font-medium bg-red-100 text-red-800 cursor-help",
                                                            tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                        )}>
                                                            <AlertTriangle className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                            Error
                                                        </span>
                                                        <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-48 p-2 bg-slate-800 text-white text-xs rounded shadow-lg z-10">
                                                            {asset.validation_errors.map((err, i) => (
                                                                <div key={i}>• {err}</div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ) : isApproved ? (
                                                    <span className={cn(
                                                        "inline-flex items-center rounded-full font-medium bg-green-100 text-green-800",
                                                        tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                    )}>
                                                        <Check className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                        Approved
                                                    </span>
                                                ) : asset.confidence_score > 0.8 ? (
                                                    <span className={cn(
                                                        "inline-flex items-center rounded-full font-medium bg-green-100 text-green-800",
                                                        tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                    )}>
                                                        High Conf.
                                                    </span>
                                                ) : (
                                                    <span className={cn(
                                                        "inline-flex items-center rounded-full font-medium bg-yellow-100 text-yellow-800",
                                                        tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                    )}>
                                                        <AlertTriangle className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                        Review
                                                    </span>
                                                )}
                                            </td>
                                            {/* Confidence - MOVED TO SECOND COLUMN */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <div className="group relative">
                                                    <span className={cn(
                                                        "font-mono cursor-help",
                                                        tableCompact ? "text-[10px]" : "text-xs",
                                                        asset.confidence_score > 0.8 ? "text-green-600" :
                                                            asset.confidence_score > 0.5 ? "text-yellow-600" : "text-red-600"
                                                    )}>
                                                        {Math.round((asset.confidence_score || 0) * 100)}%
                                                    </span>
                                                    {/* Confidence tooltip with reasoning */}
                                                    <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-64 p-3 bg-slate-800 text-white text-xs rounded shadow-lg z-10">
                                                        <div className="font-semibold mb-2">Confidence Score: {Math.round((asset.confidence_score || 0) * 100)}%</div>
                                                        <div className="space-y-1 text-slate-300">
                                                            {asset.confidence_score > 0.8 ? (
                                                                <>
                                                                    <div>✓ Description matched known asset patterns</div>
                                                                    <div>✓ Recovery period matches asset class</div>
                                                                    <div>✓ Cost within expected range</div>
                                                                </>
                                                            ) : asset.confidence_score > 0.5 ? (
                                                                <>
                                                                    <div>⚠ Partial description match</div>
                                                                    <div>⚠ Multiple possible classifications</div>
                                                                    <div className="mt-2 text-yellow-300">Recommend manual review</div>
                                                                </>
                                                            ) : (
                                                                <>
                                                                    <div>✗ Unknown or ambiguous asset type</div>
                                                                    <div>✗ Insufficient data for classification</div>
                                                                    <div className="mt-2 text-red-300">Manual classification required</div>
                                                                </>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            {/* Asset ID (Client's ID) */}
                                            <td className={cn(
                                                "font-medium text-slate-900 dark:text-white",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                {asset.asset_id || "-"}
                                            </td>
                                            {/* FA CS # (Editable - maps to FA CS numeric Asset #) */}
                                            <td className={cn(
                                                "text-slate-600",
                                                tableCompact ? "px-1 py-1" : "px-2 py-1.5"
                                            )}>
                                                <input
                                                    type="number"
                                                    min="1"
                                                    className={cn(
                                                        "w-full border rounded text-center font-mono",
                                                        tableCompact ? "px-1 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
                                                        asset.fa_cs_asset_number ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-white",
                                                        "focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                    )}
                                                    placeholder={(() => {
                                                        // Calculate auto-generated FA CS # (same logic as backend)
                                                        if (asset.asset_id) {
                                                            const match = String(asset.asset_id).match(/(\d+)/);
                                                            return match ? match[1] : String(asset.row_index);
                                                        }
                                                        return String(asset.row_index);
                                                    })()}
                                                    value={asset.fa_cs_asset_number || ""}
                                                    onChange={(e) => {
                                                        const newValue = e.target.value ? parseInt(e.target.value, 10) : null;
                                                        handleAssetUpdate(asset.unique_id, { fa_cs_asset_number: newValue });
                                                    }}
                                                    title={asset.fa_cs_asset_number
                                                        ? `Explicit FA CS #: ${asset.fa_cs_asset_number}`
                                                        : `Auto-generated from "${asset.asset_id || 'row ' + asset.row_index}". Click to override.`
                                                    }
                                                />
                                            </td>
                                            {/* Description */}
                                            <td className={cn(
                                                "text-slate-600 dark:text-slate-300 truncate",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                <span className="block truncate" title={asset.description}>
                                                    {asset.description}
                                                </span>
                                            </td>
                                            {/* Cost */}
                                            <td className={cn(
                                                "font-mono text-slate-600",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                ${(asset.cost || 0).toLocaleString()}
                                            </td>
                                            {/* Key Date - Context-aware based on transaction type */}
                                            <td className={cn(
                                                "text-slate-600",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                {(() => {
                                                    // Determine which date to display based on transaction type
                                                    if (asset.transaction_type === TRANSACTION_TYPES.DISPOSAL) {
                                                        // Disposals: Show disposal date, with tooltip for original in-service
                                                        const disposalDate = asset.disposal_date || asset.disposed_date;
                                                        if (disposalDate) {
                                                            return (
                                                                <span
                                                                    className="group relative flex items-center gap-1 cursor-help"
                                                                    title={asset.in_service_date ? `Originally in service: ${asset.in_service_date}` : ""}
                                                                >
                                                                    <span className="text-red-600">{disposalDate}</span>
                                                                    {asset.in_service_date && (
                                                                        <Info className="w-3 h-3 text-red-400" />
                                                                    )}
                                                                </span>
                                                            );
                                                        }
                                                        // Fallback if no disposal date
                                                        return (
                                                            <span className="flex items-center gap-1 text-amber-600" title="Missing disposal date">
                                                                -
                                                                <AlertTriangle className="w-3.5 h-3.5" />
                                                            </span>
                                                        );
                                                    } else if (asset.transaction_type === TRANSACTION_TYPES.TRANSFER) {
                                                        // Transfers: Show transfer date, with tooltip for original in-service
                                                        const transferDate = asset.transfer_date || asset.transferred_date;
                                                        if (transferDate) {
                                                            return (
                                                                <span
                                                                    className="group relative flex items-center gap-1 cursor-help"
                                                                    title={asset.in_service_date ? `Originally in service: ${asset.in_service_date}` : ""}
                                                                >
                                                                    <span className="text-purple-600">{transferDate}</span>
                                                                    {asset.in_service_date && (
                                                                        <Info className="w-3 h-3 text-purple-400" />
                                                                    )}
                                                                </span>
                                                            );
                                                        }
                                                        // Fallback: Use in_service_date with note for transfers
                                                        if (asset.in_service_date) {
                                                            return (
                                                                <span className="text-slate-400" title="In-service date (transfer date not provided)">
                                                                    {asset.in_service_date}
                                                                </span>
                                                            );
                                                        }
                                                        return (
                                                            <span className="text-slate-400" title="No date - transfer of existing asset">
                                                                -
                                                            </span>
                                                        );
                                                    } else {
                                                        // Additions/Existing: Show in-service date as before
                                                        if (asset.in_service_date) {
                                                            return asset.in_service_date;
                                                        } else if (asset.acquisition_date) {
                                                            return (
                                                                <span className="flex items-center gap-1" title="Using acquisition date (no in-service date provided)">
                                                                    {asset.acquisition_date}
                                                                </span>
                                                            );
                                                        }
                                                        return (
                                                            <span className="flex items-center gap-1 text-amber-600" title="Missing date - manual review required">
                                                                -
                                                                <AlertTriangle className="w-3.5 h-3.5" />
                                                            </span>
                                                        );
                                                    }
                                                })()}
                                            </td>
                                            {/* Transaction Type */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <span className={cn(
                                                    "rounded font-medium whitespace-nowrap",
                                                    tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
                                                    asset.transaction_type === TRANSACTION_TYPES.ADDITION && !isDeMinimis && "bg-green-100 text-green-700",
                                                    asset.transaction_type === TRANSACTION_TYPES.ADDITION && isDeMinimis && "bg-emerald-100 text-emerald-700",
                                                    asset.transaction_type === TRANSACTION_TYPES.EXISTING && "bg-slate-100 text-slate-700",
                                                    asset.transaction_type === TRANSACTION_TYPES.DISPOSAL && "bg-red-100 text-red-700",
                                                    asset.transaction_type === TRANSACTION_TYPES.TRANSFER && "bg-purple-100 text-purple-700",
                                                    !asset.transaction_type && "bg-yellow-100 text-yellow-700"
                                                )}>
                                                    {asset.transaction_type === TRANSACTION_TYPES.ADDITION
                                                        ? (isDeMinimis ? "Expensed" : "Addition")
                                                        : asset.transaction_type === TRANSACTION_TYPES.EXISTING
                                                            ? "Existing"
                                                            : asset.transaction_type || "Unknown"}
                                                </span>
                                            </td>

                                            {/* Class, Life, FA CS Category - Edit or Display mode */}
                                            {editingId === asset.unique_id ? (
                                                <>
                                                    <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                        <input
                                                            className={cn(
                                                                "border rounded w-full",
                                                                tableCompact ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm"
                                                            )}
                                                            value={editForm.macrs_class}
                                                            onChange={(e) => setEditForm({ ...editForm, macrs_class: e.target.value })}
                                                        />
                                                    </td>
                                                    <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                        <input
                                                            type="number"
                                                            className={cn(
                                                                "border rounded w-14",
                                                                tableCompact ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm"
                                                            )}
                                                            value={editForm.macrs_life}
                                                            onChange={(e) => setEditForm({ ...editForm, macrs_life: e.target.value })}
                                                        />
                                                    </td>
                                                    <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                        <select
                                                            className={cn(
                                                                "border rounded w-full",
                                                                tableCompact ? "px-1 py-0.5 text-xs" : "px-1.5 py-1 text-sm"
                                                            )}
                                                            value={editForm.macrs_method || ""}
                                                            onChange={(e) => setEditForm({ ...editForm, macrs_method: e.target.value })}
                                                        >
                                                            <option value="200DB">200DB</option>
                                                            <option value="150DB">150DB</option>
                                                            <option value="SL">SL</option>
                                                            <option value="ADS">ADS</option>
                                                        </select>
                                                    </td>
                                                </>
                                            ) : (
                                                <>
                                                    <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                        <span
                                                            className={cn(
                                                                "bg-blue-50 text-blue-700 rounded font-semibold border border-blue-100 cursor-help",
                                                                tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
                                                            )}
                                                            title={asset.fa_cs_wizard_category ? `FA CS: ${asset.fa_cs_wizard_category}` : ""}
                                                        >
                                                            {asset.macrs_class}
                                                        </span>
                                                    </td>
                                                    <td className={cn(
                                                        "text-slate-600",
                                                        tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                                    )}>{asset.macrs_life} yr</td>
                                                    <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                        <span className={cn(
                                                            "bg-slate-100 text-slate-700 rounded font-mono font-medium border border-slate-200",
                                                            tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs"
                                                        )}>
                                                            {asset.macrs_method || "N/A"}
                                                        </span>
                                                    </td>
                                                    {/* Election Column - 179/Bonus/DeMinimis/MACRS */}
                                                    <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                        {asset.transaction_type === "Current Year Addition" ? (
                                                            <div className="group relative">
                                                                <select
                                                                    value={asset.depreciation_election || "MACRS"}
                                                                    onChange={(e) => handleElectionChange(asset.unique_id, e.target.value)}
                                                                    className={cn(
                                                                        "rounded border font-medium cursor-pointer",
                                                                        tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs",
                                                                        asset.depreciation_election === "DeMinimis" && "bg-green-100 text-green-700 border-green-300",
                                                                        asset.depreciation_election === "Section179" && "bg-blue-100 text-blue-700 border-blue-300",
                                                                        asset.depreciation_election === "Bonus" && "bg-purple-100 text-purple-700 border-purple-300",
                                                                        (!asset.depreciation_election || asset.depreciation_election === "MACRS") && "bg-slate-100 text-slate-700 border-slate-300"
                                                                    )}
                                                                >
                                                                    <option value="MACRS">MACRS</option>
                                                                    <option value="DeMinimis">De Minimis</option>
                                                                    <option value="Section179">§179</option>
                                                                    <option value="Bonus">Bonus</option>
                                                                    <option value="ADS">ADS</option>
                                                                </select>
                                                                {/* Tooltip showing election info */}
                                                                <div className="absolute left-0 bottom-full mb-1 hidden group-hover:block w-64 p-2 bg-slate-800 text-white text-xs rounded shadow-lg z-20">
                                                                    {asset.depreciation_election === "DeMinimis" ? (
                                                                        <>
                                                                            <div className="font-semibold text-green-300 mb-1">⚡ De Minimis Safe Harbor</div>
                                                                            <div>• Expense immediately (≤$2,500)</div>
                                                                            <div>• NOT added to FA CS</div>
                                                                            <div>• Exported to separate sheet</div>
                                                                            <div className="mt-1 text-yellow-200 text-[10px]">Rev. Proc. 2015-20</div>
                                                                        </>
                                                                    ) : asset.depreciation_election === "Section179" ? (
                                                                        <>
                                                                            <div className="font-semibold text-blue-300 mb-1">§179 Expense Election</div>
                                                                            <div>• Full deduction in Year 1</div>
                                                                            <div>• Subject to business income limit</div>
                                                                            <div>• 2024 limit: $1,160,000</div>
                                                                        </>
                                                                    ) : asset.depreciation_election === "Bonus" ? (
                                                                        <>
                                                                            <div className="font-semibold text-purple-300 mb-1">Bonus Depreciation</div>
                                                                            <div>• 60% deduction in Year 1 (2024)</div>
                                                                            <div>• Remaining 40% via MACRS</div>
                                                                            <div>• No income limitation</div>
                                                                        </>
                                                                    ) : asset.depreciation_election === "ADS" ? (
                                                                        <>
                                                                            <div className="font-semibold text-slate-300 mb-1">Alternative Depreciation</div>
                                                                            <div>• Straight-line method</div>
                                                                            <div>• Longer recovery periods</div>
                                                                            <div>• Required for some property</div>
                                                                        </>
                                                                    ) : (
                                                                        <>
                                                                            <div className="font-semibold text-slate-300 mb-1">MACRS (Default)</div>
                                                                            <div>• Standard depreciation</div>
                                                                            <div>• 200DB or 150DB method</div>
                                                                            <div>• Based on property class</div>
                                                                        </>
                                                                    )}
                                                                    {asset.election_reason && (
                                                                        <div className="mt-1 pt-1 border-t border-slate-600 text-slate-300">
                                                                            {asset.election_reason}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <span className={cn(
                                                                "bg-slate-50 text-slate-400 rounded",
                                                                tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs"
                                                            )}>
                                                                N/A
                                                            </span>
                                                        )}
                                                    </td>
                                                </>
                                            )}

                                            {/* Actions */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <div className="flex gap-0.5">
                                                    {editingId === asset.unique_id ? (
                                                        <>
                                                            <button onClick={() => handleSave(asset.unique_id)} className={cn(
                                                                "hover:bg-green-100 text-green-600 rounded",
                                                                tableCompact ? "p-1" : "p-1.5"
                                                            )}>
                                                                <Save className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                            </button>
                                                            <button onClick={() => setEditingId(null)} className={cn(
                                                                "hover:bg-red-100 text-red-600 rounded",
                                                                tableCompact ? "p-1" : "p-1.5"
                                                            )}>
                                                                <X className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                            </button>
                                                        </>
                                                    ) : (
                                                        <>
                                                            {!isApproved && !hasErrors && (
                                                                <button
                                                                    onClick={() => handleApprove(asset.unique_id)}
                                                                    className={cn(
                                                                        "hover:bg-green-100 text-green-600 rounded",
                                                                        tableCompact ? "p-1" : "p-1.5"
                                                                    )}
                                                                    title="Approve"
                                                                >
                                                                    <Check className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                                </button>
                                                            )}
                                                            <button
                                                                onClick={() => handleEditClick(asset)}
                                                                className={cn(
                                                                    "hover:bg-slate-100 text-slate-600 rounded",
                                                                    tableCompact ? "p-1" : "p-1.5"
                                                                )}
                                                                title="Edit"
                                                            >
                                                                <Edit2 className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                            </button>
                                                        </>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Footer */}
            <div className="mt-4 text-sm text-slate-500 text-center">
                Showing {filteredAssets.length} of {showExistingAssets ? stats.total : stats.actionable} {showExistingAssets ? 'total' : 'actionable'} assets
                {!showExistingAssets && stats.existing > 0 && (
                    <span className="text-slate-400 ml-1">
                        ({stats.existing} existing assets hidden)
                    </span>
                )}
                {(filter !== 'all' || !showExistingAssets) && (
                    <button
                        onClick={() => { setFilter('all'); setShowExistingAssets(true); }}
                        className="ml-2 text-blue-600 hover:underline"
                    >
                        Show all {stats.total}
                    </button>
                )}
            </div>

            {/* FA CS Compatibility Check Dialog */}
            {showCompatDialog && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
                        {/* Dialog Header */}
                        <div className="p-6 border-b">
                            <div className="flex items-center gap-3">
                                <div className={cn(
                                    "h-10 w-10 rounded-full flex items-center justify-center",
                                    compatibilityCheck?.is_compatible
                                        ? "bg-green-100"
                                        : "bg-yellow-100"
                                )}>
                                    {compatibilityCheck?.is_compatible ? (
                                        <CheckCircle className="h-5 w-5 text-green-600" />
                                    ) : (
                                        <AlertTriangle className="h-5 w-5 text-yellow-600" />
                                    )}
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold">
                                        {compatibilityCheck?.is_compatible
                                            ? "Ready for FA CS Export"
                                            : "FA CS Compatibility Issues Found"
                                        }
                                    </h2>
                                    <p className="text-sm text-muted-foreground">
                                        {compatibilityCheck?.is_compatible
                                            ? "All assets passed validation checks"
                                            : `${compatibilityCheck?.issues?.length || 0} issues need attention`
                                        }
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* 179/Bonus Depreciation Preview */}
                        {depreciationPreview && (
                            <div className="p-6 bg-gradient-to-r from-blue-50 to-indigo-50 border-b">
                                <div className="flex items-center gap-2 mb-3">
                                    <Calculator className="h-5 w-5 text-blue-600" />
                                    <h3 className="font-semibold text-blue-900">Year 1 Depreciation Preview</h3>
                                </div>
                                <p className="text-xs text-blue-700 mb-3">
                                    Based on current elections, FA CS will calculate:
                                </p>
                                <div className="grid grid-cols-3 gap-4">
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-xs text-slate-500 mb-1">Section 179</div>
                                        <div className="text-lg font-bold text-green-600">
                                            ${(depreciationPreview.section_179 || 0).toLocaleString()}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-xs text-slate-500 mb-1">Bonus (60%)</div>
                                        <div className="text-lg font-bold text-blue-600">
                                            ${(depreciationPreview.bonus || 0).toLocaleString()}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-xs text-slate-500 mb-1">Regular MACRS</div>
                                        <div className="text-lg font-bold text-slate-700">
                                            ${(depreciationPreview.regular_macrs || 0).toLocaleString()}
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-3 pt-3 border-t border-blue-200">
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm font-medium text-blue-900">Total Year 1 Depreciation</span>
                                        <span className="text-xl font-bold text-blue-600">
                                            ${(depreciationPreview.total_year1 || 0).toLocaleString()}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Compatibility Issues */}
                        {compatibilityCheck?.issues?.length > 0 && (
                            <div className="p-6">
                                <div className="flex items-center justify-between mb-4">
                                    <h3 className="font-semibold">Issues to Review</h3>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={autoFixCompatibilityIssues}
                                        className="text-blue-600"
                                    >
                                        <Wand2 className="h-4 w-4 mr-1" />
                                        Auto-Fix All
                                    </Button>
                                </div>
                                <div className="space-y-2 max-h-60 overflow-y-auto">
                                    {compatibilityCheck.issues.map((issue, idx) => (
                                        <div
                                            key={idx}
                                            className={cn(
                                                "p-3 rounded-lg border text-sm",
                                                issue.severity === 'error'
                                                    ? "bg-red-50 border-red-200"
                                                    : "bg-yellow-50 border-yellow-200"
                                            )}
                                        >
                                            <div className="flex items-start gap-2">
                                                {issue.severity === 'error' ? (
                                                    <X className="h-4 w-4 text-red-500 mt-0.5" />
                                                ) : (
                                                    <AlertTriangle className="h-4 w-4 text-yellow-500 mt-0.5" />
                                                )}
                                                <div className="flex-1">
                                                    <div className="font-medium">{issue.asset_id}</div>
                                                    <div className="text-muted-foreground">{issue.message}</div>
                                                    {issue.suggestion && (
                                                        <div className="text-xs text-blue-600 mt-1">
                                                            Suggestion: {issue.suggestion}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Dialog Actions */}
                        <div className="p-6 border-t bg-slate-50 flex justify-end gap-3">
                            <Button
                                variant="outline"
                                onClick={() => setShowCompatDialog(false)}
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={() => {
                                    setShowCompatDialog(false);
                                    handleExport();
                                }}
                                disabled={!compatibilityCheck?.is_compatible}
                                className={cn(
                                    "text-white",
                                    compatibilityCheck?.is_compatible
                                        ? "bg-green-600 hover:bg-green-700"
                                        : "bg-gray-400 cursor-not-allowed"
                                )}
                            >
                                <Download className="w-4 h-4 mr-2" />
                                {compatibilityCheck?.is_compatible
                                    ? "Export Now"
                                    : "Fix Issues First"
                                }
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export { Review };
export default Review;
