import React, { useState, useMemo, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Check, X, AlertTriangle, Edit2, Save, CheckCircle, Filter, Download, Info, AlertOctagon, Car, Eye, EyeOff, FileText } from 'lucide-react';
import { cn } from '../lib/utils';
import axios from 'axios';

function Review({ assets = [] }) {
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const [localAssets, setLocalAssets] = useState(assets);
    const [filter, setFilter] = useState('all'); // all, errors, review, approved
    const [showExistingAssets, setShowExistingAssets] = useState(false); // Hide existing by default
    const [approvedIds, setApprovedIds] = useState(new Set());
    const [warnings, setWarnings] = useState({ critical: [], warnings: [], info: [], summary: {} });
    const [taxYear, setTaxYear] = useState(new Date().getFullYear());
    const [tableCompact, setTableCompact] = useState(false); // Table density: false = comfortable, true = compact

    // Fetch warnings when assets change
    useEffect(() => {
        if (assets.length > 0) {
            fetchWarnings();
            fetchTaxConfig();
        }
    }, [assets]);

    const fetchWarnings = async () => {
        try {
            const response = await axios.get('http://127.0.0.1:8000/warnings');
            setWarnings(response.data);
        } catch (error) {
            console.error('Failed to fetch warnings:', error);
        }
    };

    const fetchTaxConfig = async () => {
        try {
            const response = await axios.get('http://127.0.0.1:8000/config/tax');
            setTaxYear(response.data.tax_year);
        } catch (error) {
            console.error('Failed to fetch tax config:', error);
        }
    };

    // Sync local assets when props change
    React.useEffect(() => {
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
        const additions = localAssets.filter(a =>
            a.transaction_type === "Current Year Addition"
        ).length;
        const disposals = localAssets.filter(a =>
            a.transaction_type === "Disposal"
        ).length;
        const transfers = localAssets.filter(a =>
            a.transaction_type === "Transfer"
        ).length;
        const existing = localAssets.filter(a =>
            a.transaction_type === "Existing Asset"
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
                a.transaction_type !== "Existing Asset"
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
                return baseAssets.filter(a => approvedIds.has(a.row_index));
            default:
                return baseAssets;
        }
    }, [localAssets, filter, approvedIds, showExistingAssets]);

    // Check if export should be disabled
    const hasBlockingErrors = stats.errors > 0;
    const allReviewed = stats.needsReview === 0 ||
        localAssets.filter(a => !a.validation_errors?.length && a.confidence_score <= 0.8)
            .every(a => approvedIds.has(a.row_index));

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
        setEditingId(asset.row_index);
        setEditForm({
            macrs_class: asset.macrs_class,
            macrs_life: asset.macrs_life,
            macrs_method: asset.macrs_method,
            fa_cs_wizard_category: asset.fa_cs_wizard_category
        });
    };

    const handleSave = async (rowIndex) => {
        try {
            // Include fa_cs_wizard_category in the update
            const updateData = {
                ...editForm,
                fa_cs_wizard_category: editForm.fa_cs_wizard_category
            };
            const updatedAssets = localAssets.map(a =>
                a.row_index === rowIndex ? { ...a, ...updateData, confidence_score: 1.0 } : a
            );
            setLocalAssets(updatedAssets);
            setEditingId(null);
            setApprovedIds(prev => new Set([...prev, rowIndex]));

            await axios.post(`http://127.0.0.1:8000/assets/${rowIndex}/update`, updateData);
        } catch (error) {
            console.error("Failed to save update:", error);
        }
    };

    const handleApprove = (rowIndex) => {
        setApprovedIds(prev => new Set([...prev, rowIndex]));
    };

    const handleApproveAllHighConfidence = () => {
        const highConfIds = localAssets
            .filter(a => !a.validation_errors?.length && a.confidence_score > 0.8)
            .map(a => a.row_index);
        setApprovedIds(prev => new Set([...prev, ...highConfIds]));
    };

    // Helper function to download file without opening new window (works in Electron)
    const downloadFile = async (url, defaultFilename) => {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                const errorText = await response.text();
                alert(`Download failed: ${errorText}`);
                return;
            }

            // Get filename from Content-Disposition header or use default
            const disposition = response.headers.get('Content-Disposition');
            let filename = defaultFilename;
            if (disposition) {
                const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                if (match && match[1]) {
                    filename = match[1].replace(/['"]/g, '');
                }
            }

            // Download as blob and trigger save
            const blob = await response.blob();
            const blobUrl = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (error) {
            alert(`Download error: ${error.message}`);
        }
    };

    const handleExport = () => {
        downloadFile('http://127.0.0.1:8000/export', 'FA_CS_Import.xlsx');
    };

    const handleAuditReport = () => {
        downloadFile('http://127.0.0.1:8000/export/audit', 'Audit_Report.xlsx');
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
                        <span className="px-3 py-1 text-sm font-semibold bg-blue-100 text-blue-800 rounded-full border border-blue-200">
                            Tax Year {taxYear}
                        </span>
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
                        onClick={handleExport}
                        disabled={hasBlockingErrors}
                        className={cn(
                            "text-white",
                            hasBlockingErrors
                                ? "bg-gray-400 cursor-not-allowed"
                                : "bg-green-600 hover:bg-green-700"
                        )}
                    >
                        <Download className="w-4 h-4 mr-2" />
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
                            {stats.additions} Additions
                        </span>
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
                            "w-full text-left min-w-[1400px]",
                            tableCompact ? "text-xs" : "text-sm"
                        )}>
                            <thead className={cn(
                                "text-xs text-slate-500 uppercase bg-slate-50 dark:bg-slate-900/50 border-b",
                                tableCompact ? "text-[10px]" : "text-xs"
                            )}>
                                <tr>
                                    <th className={cn("w-20", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Asset ID</th>
                                    <th className={cn("min-w-[200px]", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Description</th>
                                    <th className={cn("w-24", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Cost</th>
                                    <th className={cn("w-28", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Date in Service</th>
                                    <th className={cn("w-24", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Trans. Type</th>
                                    <th className={cn("w-28", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Class</th>
                                    <th className={cn("w-14", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Life</th>
                                    <th className={cn("min-w-[280px]", tableCompact ? "px-2 py-2" : "px-3 py-3")}>FA CS Category</th>
                                    <th className={cn("w-24", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Status</th>
                                    <th className={cn("w-14", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Conf.</th>
                                    <th className={cn("w-20", tableCompact ? "px-2 py-2" : "px-3 py-3")}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredAssets.map((asset, index) => {
                                    const isApproved = approvedIds.has(asset.row_index);
                                    const hasErrors = asset.validation_errors?.length > 0;
                                    const needsReview = !hasErrors && asset.confidence_score <= 0.8;

                                    return (
                                        <tr
                                            key={index}
                                            className={cn(
                                                "border-b hover:bg-slate-50 dark:border-slate-800",
                                                hasErrors && "bg-red-50/50",
                                                needsReview && !isApproved && "bg-yellow-50/30",
                                                isApproved && "bg-green-50/30"
                                            )}
                                        >
                                            {/* Asset ID */}
                                            <td className={cn(
                                                "font-medium text-slate-900 dark:text-white",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                {asset.asset_id || "-"}
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
                                            {/* Date in Service */}
                                            <td className={cn(
                                                "text-slate-600",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                {asset.date_in_service ? (
                                                    asset.date_in_service
                                                ) : asset.acquisition_date ? (
                                                    <span className="flex items-center gap-1" title="Using acquisition date (no in-service date provided)">
                                                        <span className={asset.transaction_type === "Transfer" ? "text-amber-600" : ""}>
                                                            {asset.acquisition_date}
                                                        </span>
                                                        {asset.transaction_type === "Transfer" && (
                                                            <Info className="w-3.5 h-3.5 text-amber-500" />
                                                        )}
                                                    </span>
                                                ) : (
                                                    <span className={cn(
                                                        "flex items-center gap-1",
                                                        asset.transaction_type === "Transfer" ? "text-slate-400" : "text-amber-600"
                                                    )} title={asset.transaction_type === "Transfer" ? "No date - transfer of existing asset" : "Missing date - manual review required"}>
                                                        -
                                                        {asset.transaction_type !== "Transfer" && (
                                                            <AlertTriangle className="w-3.5 h-3.5" />
                                                        )}
                                                    </span>
                                                )}
                                            </td>
                                            {/* Transaction Type */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <span className={cn(
                                                    "rounded font-medium whitespace-nowrap",
                                                    tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
                                                    asset.transaction_type === "Current Year Addition" && "bg-green-100 text-green-700",
                                                    asset.transaction_type === "Existing Asset" && "bg-slate-100 text-slate-700",
                                                    asset.transaction_type === "Disposal" && "bg-red-100 text-red-700",
                                                    asset.transaction_type === "Transfer" && "bg-purple-100 text-purple-700",
                                                    !asset.transaction_type && "bg-yellow-100 text-yellow-700"
                                                )}>
                                                    {asset.transaction_type === "Current Year Addition" ? "Addition" :
                                                     asset.transaction_type === "Existing Asset" ? "Existing" :
                                                     asset.transaction_type || "Unknown"}
                                                </span>
                                            </td>

                                            {/* Class, Life, FA CS Category - Edit or Display mode */}
                                            {editingId === asset.row_index ? (
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
                                                                tableCompact ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm"
                                                            )}
                                                            value={editForm.fa_cs_wizard_category || ""}
                                                            onChange={(e) => setEditForm({ ...editForm, fa_cs_wizard_category: e.target.value })}
                                                        >
                                                            <option value="">Select FA CS Category...</option>
                                                            {Object.entries(FA_CS_WIZARD_OPTIONS).flatMap(([life, options]) =>
                                                                options.map(opt => (
                                                                    <option key={opt} value={opt}>{opt}</option>
                                                                ))
                                                            )}
                                                        </select>
                                                    </td>
                                                </>
                                            ) : (
                                                <>
                                                    <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                        <span className={cn(
                                                            "bg-blue-50 text-blue-700 rounded font-semibold border border-blue-100",
                                                            tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
                                                        )}>
                                                            {asset.macrs_class}
                                                        </span>
                                                    </td>
                                                    <td className={cn(
                                                        "text-slate-600",
                                                        tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                                    )}>{asset.macrs_life} yr</td>
                                                    <td className={cn(
                                                        "text-slate-600",
                                                        tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                                    )}>
                                                        <span
                                                            className="block truncate cursor-help"
                                                            title={asset.fa_cs_wizard_category || asset.macrs_method}
                                                        >
                                                            {asset.fa_cs_wizard_category || asset.macrs_method}
                                                        </span>
                                                    </td>
                                                </>
                                            )}

                                            {/* Status */}
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
                                                        <div className="absolute right-0 bottom-full mb-2 hidden group-hover:block w-48 p-2 bg-slate-800 text-white text-xs rounded shadow-lg z-10">
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
                                            {/* Confidence */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <span className={cn(
                                                    "font-mono",
                                                    tableCompact ? "text-[10px]" : "text-xs",
                                                    asset.confidence_score > 0.8 ? "text-green-600" :
                                                        asset.confidence_score > 0.5 ? "text-yellow-600" : "text-red-600"
                                                )}>
                                                    {Math.round((asset.confidence_score || 0) * 100)}%
                                                </span>
                                            </td>
                                            {/* Actions */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <div className="flex gap-0.5">
                                                    {editingId === asset.row_index ? (
                                                        <>
                                                            <button onClick={() => handleSave(asset.row_index)} className={cn(
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
                                                                    onClick={() => handleApprove(asset.row_index)}
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
        </div>
    );
}

export { Review };
export default Review;
