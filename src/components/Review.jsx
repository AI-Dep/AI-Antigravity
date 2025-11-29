import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Check, X, AlertTriangle, Edit2, Save } from 'lucide-react';
import { cn } from '@/lib/utils';
import axios from 'axios';

export function Review({ assets = [] }) {
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const [localAssets, setLocalAssets] = useState(assets);

    // Sync local assets when props change
    React.useEffect(() => {
        setLocalAssets(assets);
    }, [assets]);

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
            // Optimistic Update
            const updatedAssets = localAssets.map(a =>
                a.row_index === rowIndex ? { ...a, ...editForm } : a
            );
            setLocalAssets(updatedAssets);
            setEditingId(null);

            // Send to Backend
            await axios.post(`http://127.0.0.1:8000/assets/${rowIndex}/update`, editForm);

        } catch (error) {
            console.error("Failed to save update:", error);
            // Revert on failure (optional, for now just log)
        }
    };

    const handleExport = () => {
        // Trigger download
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
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">Review & Approve</h1>
                    <p className="text-slate-500 dark:text-slate-400 mt-2">
                        Review AI classifications. Edits are automatically audited.
                    </p>
                </div>
                <div className="flex gap-4">
                    <Button variant="outline" className="text-red-600 hover:text-red-700 hover:bg-red-50">
                        Discard All
                    </Button>
                    <Button onClick={handleExport} className="bg-green-600 hover:bg-green-700 text-white">
                        Export to FA CS
                    </Button>
                </div>
            </div>

            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs text-slate-500 uppercase bg-slate-50 dark:bg-slate-900/50 border-b">
                                <tr>
                                    <th className="px-6 py-3">Status</th>
                                    <th className="px-6 py-3">Asset ID</th>
                                    <th className="px-6 py-3">Description</th>
                                    <th className="px-6 py-3">Cost</th>
                                    <th className="px-6 py-3">Class</th>
                                    <th className="px-6 py-3">Life</th>
                                    <th className="px-6 py-3">Method</th>
                                    <th className="px-6 py-3">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {localAssets.map((asset, index) => (
                                    <tr key={index} className="bg-white border-b hover:bg-slate-50 dark:bg-slate-950 dark:border-slate-800">
                                        <td className="px-6 py-4">
                                            {asset.validation_errors && asset.validation_errors.length > 0 ? (
                                                <div className="group relative flex items-center">
                                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 cursor-help">
                                                        <AlertTriangle className="w-3 h-3 mr-1" />
                                                        Invalid
                                                    </span>
                                                    <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-48 p-2 bg-slate-800 text-white text-xs rounded shadow-lg z-10">
                                                        {asset.validation_errors.map((err, i) => (
                                                            <div key={i}>• {err}</div>
                                                        ))}
                                                    </div>
                                                </div>
                                            ) : asset.confidence_score > 0.8 ? (
                                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                                    High Confidence
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                                                    <AlertTriangle className="w-3 h-3 mr-1" />
                                                    Review
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">
                                            {asset.asset_id || "-"}
                                        </td>
                                        <td className="px-6 py-4 text-slate-600 dark:text-slate-300">
                                            {asset.description}
                                        </td>
                                        <td className="px-6 py-4 font-mono text-slate-600">
                                            ${asset.cost.toLocaleString()}
                                        </td>

                                        {/* Editable Fields */}
                                        {editingId === asset.row_index ? (
                                            <>
                                                <td className="px-6 py-4">
                                                    <input
                                                        className="border rounded px-2 py-1 w-full"
                                                        value={editForm.macrs_class}
                                                        onChange={(e) => setEditForm({ ...editForm, macrs_class: e.target.value })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4">
                                                    <input
                                                        type="number"
                                                        className="border rounded px-2 py-1 w-20"
                                                        value={editForm.macrs_life}
                                                        onChange={(e) => setEditForm({ ...editForm, macrs_life: e.target.value })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4">
                                                    <input
                                                        className="border rounded px-2 py-1 w-24"
                                                        value={editForm.macrs_method}
                                                        onChange={(e) => setEditForm({ ...editForm, macrs_method: e.target.value })}
                                                    />
                                                </td>
                                                <td className="px-6 py-4">
                                                    <button onClick={() => handleSave(asset.row_index)} className="p-1 hover:bg-green-100 text-green-600 rounded mr-2">
                                                        <Save className="w-4 h-4" />
                                                    </button>
                                                    <button onClick={() => setEditingId(null)} className="p-1 hover:bg-red-100 text-red-600 rounded">
                                                        <X className="w-4 h-4" />
                                                    </button>
                                                </td>
                                            </>
                                        ) : (
                                            <>
                                                <td className="px-6 py-4">
                                                    <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs font-semibold border border-blue-100">
                                                        {asset.macrs_class}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4">{asset.macrs_life} yr</td>
                                                <td className="px-6 py-4">{asset.macrs_method}</td>
                                                <td className="px-6 py-4">
                                                    <div className="flex gap-2">
                                                        <button onClick={() => handleEditClick(asset)} className="p-1 hover:bg-slate-100 text-slate-600 rounded">
                                                            <Edit2 className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </td>
                                            </>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
