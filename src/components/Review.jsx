import React, { useState, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Check, X, AlertTriangle, Edit2, Save, CheckCircle, Filter, Download } from 'lucide-react';
import { cn } from '../lib/utils';
import axios from 'axios';

export default function Review({ assets = [] }) {
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const [localAssets, setLocalAssets] = useState(assets);
    const [filter, setFilter] = useState('all'); // all, errors, review, approved
    const [approvedIds, setApprovedIds] = useState(new Set());

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

        return {
            total: localAssets.length,
            errors,
            needsReview,
            highConfidence,
            approved,
            totalCost
        };
    }, [localAssets, approvedIds]);

    // Filter assets
    const filteredAssets = useMemo(() => {
        switch (filter) {
            case 'errors':
                return localAssets.filter(a => a.validation_errors?.length > 0);
            case 'review':
                return localAssets.filter(a =>
                    !a.validation_errors?.length && a.confidence_score <= 0.8
                );
            case 'approved':
                return localAssets.filter(a => approvedIds.has(a.row_index));
            default:
                return localAssets;
        }
    }, [localAssets, filter, approvedIds]);

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
                Showing {filteredAssets.length} of {stats.total} assets
                {filter !== 'all' && (
                    <button
                        onClick={() => setFilter('all')}
                        className="ml-2 text-blue-600 hover:underline"
                    >
                        Show all
                    </button>
                )}
            </div>
        </div>
    );
}
