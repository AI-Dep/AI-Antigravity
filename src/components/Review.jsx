import React, { useState, useMemo, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Check, X, AlertTriangle, Edit2, Save, CheckCircle, Filter, Download, Info, ChevronDown, ChevronUp, Shield, AlertOctagon, Car, Eye, EyeOff, FileText } from 'lucide-react';
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
    const [confidence, setConfidence] = useState({ high: {}, medium: {}, low: {}, total: 0 });
    const [showConfidenceBreakdown, setShowConfidenceBreakdown] = useState(false);

    // Fetch warnings and confidence when assets change
    useEffect(() => {
        if (assets.length > 0) {
            fetchWarnings();
            fetchTaxConfig();
            fetchConfidence();
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

    const fetchConfidence = async () => {
        try {
            const response = await axios.get('http://127.0.0.1:8000/confidence');
            setConfidence(response.data);
        } catch (error) {
            console.error('Failed to fetch confidence:', error);
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

    const handleEditClick = (asset) => {
        setEditingId(asset.row_index);
        setEditForm({
            macrs_class: asset.macrs_class,
            macrs_life: asset.macrs_life,
            macrs_method: asset.macrs_method
        });
    };

    const handleSave = async (rowIndex) => {
        try {
            const updatedAssets = localAssets.map(a =>
                a.row_index === rowIndex ? { ...a, ...editForm, confidence_score: 1.0 } : a
            );
            setLocalAssets(updatedAssets);
            setEditingId(null);
            setApprovedIds(prev => new Set([...prev, rowIndex]));

            await axios.post(`http://127.0.0.1:8000/assets/${rowIndex}/update`, editForm);
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

    const handleExport = () => {
        window.open('http://127.0.0.1:8000/export', '_blank');
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
        <div className="p-8 max-w-[1600px] mx-auto">
            {/* Header */}
            <div className="flex justify-between items-start mb-6">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                        Review & Approve
                    </h1>
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
                        onClick={() => window.open('http://127.0.0.1:8000/export/audit', '_blank')}
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

            {/* Confidence Breakdown - Collapsible */}
            {confidence.total > 0 && (
                <Card className="mb-4">
                    <div
                        className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-50 transition-colors"
                        onClick={() => setShowConfidenceBreakdown(!showConfidenceBreakdown)}
                    >
                        <div className="flex items-center gap-4">
                            <Shield className="w-5 h-5 text-blue-600" />
                            <div>
                                <div className="font-semibold text-sm">Classification Confidence Breakdown</div>
                                <div className="text-xs text-muted-foreground">
                                    {confidence.auto_approve_eligible || 0} assets eligible for auto-approval
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            {/* Mini confidence bars */}
                            <div className="flex items-center gap-2 text-xs">
                                <span className="text-green-600">{confidence.high?.count || 0} high</span>
                                <span className="text-yellow-600">{confidence.medium?.count || 0} med</span>
                                <span className="text-red-600">{confidence.low?.count || 0} low</span>
                            </div>
                            {showConfidenceBreakdown ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </div>
                    </div>

                    {showConfidenceBreakdown && (
                        <CardContent className="pt-0 pb-4">
                            <div className="grid grid-cols-3 gap-4">
                                <div className="p-3 bg-green-50 rounded-lg border border-green-200">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs font-medium text-green-700">High Confidence</span>
                                        <span className="text-xs text-green-600">80%+</span>
                                    </div>
                                    <div className="text-2xl font-bold text-green-600">{confidence.high?.count || 0}</div>
                                    <div className="text-xs text-green-600 mt-1">
                                        {confidence.high?.pct || 0}% of assets - Auto-approve eligible
                                    </div>
                                </div>
                                <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs font-medium text-yellow-700">Medium Confidence</span>
                                        <span className="text-xs text-yellow-600">50-80%</span>
                                    </div>
                                    <div className="text-2xl font-bold text-yellow-600">{confidence.medium?.count || 0}</div>
                                    <div className="text-xs text-yellow-600 mt-1">
                                        {confidence.medium?.pct || 0}% of assets - Quick review needed
                                    </div>
                                </div>
                                <div className="p-3 bg-red-50 rounded-lg border border-red-200">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs font-medium text-red-700">Low Confidence</span>
                                        <span className="text-xs text-red-600">&lt;50%</span>
                                    </div>
                                    <div className="text-2xl font-bold text-red-600">{confidence.low?.count || 0}</div>
                                    <div className="text-xs text-red-600 mt-1">
                                        {confidence.low?.pct || 0}% of assets - CPA attention required
                                    </div>
                                </div>
                            </div>
                            <div className="mt-3 text-xs text-muted-foreground text-center">
                                Classification sources: Rule-based (85-98%), Client Category (85%), GPT Fallback (50-90%), Keyword Match (70-80%)
                            </div>
                        </CardContent>
                    )}
                </Card>
            )}

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

            {/* Transaction Type Summary */}
            {warnings.info?.find(i => i.type === 'TRANSACTION_SUMMARY') && (
                <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Info className="w-4 h-4 text-blue-600" />
                        <span className="text-sm text-blue-800">
                            Tax Year {taxYear} | Transaction Types:
                        </span>
                        {Object.entries(
                            warnings.info.find(i => i.type === 'TRANSACTION_SUMMARY')?.breakdown || {}
                        ).map(([type, count]) => (
                            <span key={type} className="text-sm bg-blue-100 px-2 py-0.5 rounded text-blue-700">
                                {type}: {count}
                            </span>
                        ))}
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
                {!showExistingAssets && stats.existing > 0 && (
                    <div className="text-xs text-slate-500 flex items-center gap-1">
                        <EyeOff className="w-3 h-3" />
                        {stats.existing} existing assets hidden (no action required)
                    </div>
                )}
            </div>

            {/* Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs text-slate-500 uppercase bg-slate-50 dark:bg-slate-900/50 border-b">
                                <tr>
                                    <th className="px-4 py-3 w-32">Status</th>
                                    <th className="px-4 py-3 w-16">Conf.</th>
                                    <th className="px-4 py-3">Asset ID</th>
                                    <th className="px-4 py-3">Description</th>
                                    <th className="px-4 py-3">Cost</th>
                                    <th className="px-4 py-3">Trans. Type</th>
                                    <th className="px-4 py-3">Class</th>
                                    <th className="px-4 py-3">Life</th>
                                    <th className="px-4 py-3">Method</th>
                                    <th className="px-4 py-3 w-32">Actions</th>
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
                                            <td className="px-4 py-3">
                                                {hasErrors ? (
                                                    <div className="group relative flex items-center">
                                                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 cursor-help">
                                                            <AlertTriangle className="w-3 h-3 mr-1" />
                                                            Error
                                                        </span>
                                                        <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-48 p-2 bg-slate-800 text-white text-xs rounded shadow-lg z-10">
                                                            {asset.validation_errors.map((err, i) => (
                                                                <div key={i}>• {err}</div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ) : isApproved ? (
                                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                                        <Check className="w-3 h-3 mr-1" />
                                                        Approved
                                                    </span>
                                                ) : asset.confidence_score > 0.8 ? (
                                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                                        High Conf.
                                                    </span>
                                                ) : (
                                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                                                        <AlertTriangle className="w-3 h-3 mr-1" />
                                                        Review
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={cn(
                                                    "text-xs font-mono",
                                                    asset.confidence_score > 0.8 ? "text-green-600" :
                                                        asset.confidence_score > 0.5 ? "text-yellow-600" : "text-red-600"
                                                )}>
                                                    {Math.round((asset.confidence_score || 0) * 100)}%
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">
                                                {asset.asset_id || "-"}
                                            </td>
                                            <td className="px-4 py-3 text-slate-600 dark:text-slate-300 max-w-xs truncate">
                                                {asset.description}
                                            </td>
                                            <td className="px-4 py-3 font-mono text-slate-600">
                                                ${(asset.cost || 0).toLocaleString()}
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={cn(
                                                    "px-2 py-1 rounded text-xs font-medium",
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

                                            {editingId === asset.row_index ? (
                                                <>
                                                    <td className="px-4 py-3">
                                                        <input
                                                            className="border rounded px-2 py-1 w-full text-sm"
                                                            value={editForm.macrs_class}
                                                            onChange={(e) => setEditForm({ ...editForm, macrs_class: e.target.value })}
                                                        />
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <input
                                                            type="number"
                                                            className="border rounded px-2 py-1 w-16 text-sm"
                                                            value={editForm.macrs_life}
                                                            onChange={(e) => setEditForm({ ...editForm, macrs_life: e.target.value })}
                                                        />
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <input
                                                            className="border rounded px-2 py-1 w-20 text-sm"
                                                            value={editForm.macrs_method}
                                                            onChange={(e) => setEditForm({ ...editForm, macrs_method: e.target.value })}
                                                        />
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <button onClick={() => handleSave(asset.row_index)} className="p-1.5 hover:bg-green-100 text-green-600 rounded mr-1">
                                                            <Save className="w-4 h-4" />
                                                        </button>
                                                        <button onClick={() => setEditingId(null)} className="p-1.5 hover:bg-red-100 text-red-600 rounded">
                                                            <X className="w-4 h-4" />
                                                        </button>
                                                    </td>
                                                </>
                                            ) : (
                                                <>
                                                    <td className="px-4 py-3">
                                                        <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs font-semibold border border-blue-100">
                                                            {asset.macrs_class}
                                                        </span>
                                                    </td>
                                                    <td className="px-4 py-3 text-slate-600">{asset.macrs_life} yr</td>
                                                    <td className="px-4 py-3 text-slate-600">{asset.macrs_method}</td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex gap-1">
                                                            {!isApproved && !hasErrors && (
                                                                <button
                                                                    onClick={() => handleApprove(asset.row_index)}
                                                                    className="p-1.5 hover:bg-green-100 text-green-600 rounded"
                                                                    title="Approve"
                                                                >
                                                                    <Check className="w-4 h-4" />
                                                                </button>
                                                            )}
                                                            <button
                                                                onClick={() => handleEditClick(asset)}
                                                                className="p-1.5 hover:bg-slate-100 text-slate-600 rounded"
                                                                title="Edit"
                                                            >
                                                                <Edit2 className="w-4 h-4" />
                                                            </button>
                                                        </div>
                                                    </td>
                                                </>
                                            )}
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
