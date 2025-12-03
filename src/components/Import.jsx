import React, { useState, useRef } from 'react';
import { Upload, AlertCircle, CheckCircle, ChevronDown, ChevronUp, Info, X } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '../lib/utils';
import { apiGet, apiUpload } from '../lib/api.client';

function Import({ onUploadSuccess }) {
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState(null);
    const [tabAnalysis, setTabAnalysis] = useState(null);
    const [showTabDetails, setShowTabDetails] = useState(false);
    const fileInputRef = useRef(null);
    const dragCounterRef = useRef(0); // Track drag enter/leave to handle child elements

    // Fetch tab analysis after successful upload
    const fetchTabAnalysis = async () => {
        try {
            const data = await apiGet('/tabs');
            if (data.tabs?.length > 0) {
                setTabAnalysis(data);
            }
        } catch (err) {
            // Non-fatal - tab analysis is optional
        }
    };

    const handleDragEnter = (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current++;
        if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
            setIsDragging(true);
        }
    };

    const handleDragOver = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current--;
        if (dragCounterRef.current === 0) {
            setIsDragging(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
        dragCounterRef.current = 0;
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFiles(files[0]);
        }
    };

    const handleFiles = async (file) => {
        if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
            setError("Please upload a valid Excel file (.xlsx or .xls)");
            return;
        }

        setError(null);
        setIsUploading(true);
        setTabAnalysis(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Send to Python Backend using centralized API client
            const data = await apiUpload('/upload', formData);

            // Fetch tab analysis
            await fetchTabAnalysis();

            // Success! Pass data up to App
            onUploadSuccess(data);

        } catch (err) {
            console.error("Upload failed:", err);
            // Show detailed error message from API client
            if (err.message) {
                setError(`Error: ${err.message}`);
            } else {
                setError("Failed to process file. Is the backend running?");
            }
        } finally {
            setIsUploading(false);
            // Reset file input so same file can be re-uploaded
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
    };

    // Get role badge color
    const getRoleBadgeClass = (role) => {
        const colors = {
            'detail': 'bg-green-100 text-green-700',
            'additions': 'bg-green-100 text-green-700',
            'summary': 'bg-slate-100 text-slate-600',
            'disposals': 'bg-red-100 text-red-700',
            'transfers': 'bg-purple-100 text-purple-700',
            'prior_year': 'bg-yellow-100 text-yellow-700',
            'working': 'bg-slate-100 text-slate-500',
            'unknown': 'bg-orange-100 text-orange-700',
        };
        return colors[role] || colors.unknown;
    };

    return (
        <div className="p-8 max-w-4xl mx-auto">
            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">Import Data</h1>
                <p className="text-slate-500 dark:text-slate-400 mt-2">Upload client asset schedules for AI analysis.</p>
            </div>

            <Card className="border-dashed border-2">
                <CardContent className="p-12">
                    <div
                        className={cn(
                            "flex flex-col items-center justify-center p-12 rounded-xl transition-all duration-200 cursor-pointer",
                            isDragging ? "bg-blue-50 border-blue-500" : "bg-slate-50 border-slate-200 hover:bg-slate-100",
                            isUploading && "opacity-50 pointer-events-none"
                        )}
                        onDragEnter={handleDragEnter}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <input
                            type="file"
                            ref={fileInputRef}
                            className="hidden"
                            accept=".xlsx,.xls"
                            onChange={(e) => e.target.files.length > 0 && handleFiles(e.target.files[0])}
                        />

                        <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mb-6">
                            {isUploading ? (
                                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
                            ) : (
                                <Upload className="w-10 h-10 text-blue-600" />
                            )}
                        </div>

                        <h3 className="text-xl font-semibold text-slate-900 mb-2">
                            {isUploading ? "Analyzing Assets..." : "Drag & Drop Excel File"}
                        </h3>
                        <p className="text-slate-500 text-center max-w-sm mb-6">
                            {isUploading ? "Our AI is classifying your assets. This may take a moment." : "Or click to browse from your computer. Supported formats: .xlsx, .xls"}
                        </p>

                        <Button disabled={isUploading}>
                            {isUploading ? "Processing..." : "Select File"}
                        </Button>
                    </div>

                    {error && (
                        <div className="mt-6 p-4 bg-red-50 text-red-700 rounded-lg flex items-center">
                            <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
                            {error}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Tab Analysis Results - Collapsible */}
            {tabAnalysis && tabAnalysis.tabs?.length > 0 && (
                <Card className="mt-6">
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-lg">Tab Analysis</CardTitle>
                                <CardDescription>
                                    {tabAnalysis.filename} - {tabAnalysis.tabs.length} sheets detected
                                </CardDescription>
                            </div>
                            <button
                                onClick={() => setShowTabDetails(!showTabDetails)}
                                className="p-2 text-muted-foreground hover:text-foreground hover:bg-slate-100 rounded-lg transition-colors"
                            >
                                {showTabDetails ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                            </button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        {/* Summary Stats */}
                        <div className="flex gap-4 mb-4">
                            <div className="flex items-center gap-2 px-3 py-2 bg-green-50 rounded-lg">
                                <CheckCircle className="w-4 h-4 text-green-600" />
                                <span className="text-sm">
                                    <strong>{tabAnalysis.efficiency?.process_tabs || 0}</strong> tabs processed
                                </span>
                            </div>
                            <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 rounded-lg">
                                <X className="w-4 h-4 text-slate-500" />
                                <span className="text-sm">
                                    <strong>{tabAnalysis.efficiency?.skip_tabs || 0}</strong> tabs skipped
                                </span>
                            </div>
                            {tabAnalysis.efficiency?.reduction_percent > 0 && (
                                <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 rounded-lg">
                                    <Info className="w-4 h-4 text-blue-600" />
                                    <span className="text-sm text-blue-700">
                                        {tabAnalysis.efficiency.reduction_percent.toFixed(0)}% efficiency gain
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* Warnings and Auto-Detection Messages */}
                        {tabAnalysis.warnings?.length > 0 && (
                            <div className="mb-4 space-y-2">
                                {tabAnalysis.warnings.map((warning, idx) => (
                                    <div
                                        key={idx}
                                        className={cn(
                                            "p-3 rounded-lg text-sm border",
                                            warning.includes("Auto-detected fiscal year")
                                                ? "bg-blue-50 border-blue-200 text-blue-800"
                                                : "bg-yellow-50 border-yellow-200 text-yellow-800"
                                        )}
                                    >
                                        {warning.includes("Auto-detected fiscal year") && (
                                            <span className="font-semibold">🎯 </span>
                                        )}
                                        {warning}
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Detailed Tab List - Collapsible */}
                        {showTabDetails && (
                            <div className="space-y-2 pt-4 border-t">
                                {tabAnalysis.tabs.map((tab, idx) => (
                                    <div
                                        key={idx}
                                        className={cn(
                                            "flex items-center justify-between p-3 rounded-lg border",
                                            tab.should_process
                                                ? "bg-green-50/50 border-green-200"
                                                : "bg-slate-50 border-slate-200"
                                        )}
                                    >
                                        <div className="flex items-center gap-3">
                                            <span className="text-lg">{tab.icon}</span>
                                            <div>
                                                <div className="font-medium text-sm">{tab.tab_name}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {tab.data_row_count} data rows
                                                    {tab.fiscal_year && ` | FY ${tab.fiscal_year}`}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className={cn(
                                                "px-2 py-1 text-xs font-medium rounded",
                                                getRoleBadgeClass(tab.role)
                                            )}>
                                                {tab.role_label}
                                            </span>
                                            {tab.should_process ? (
                                                <CheckCircle className="w-4 h-4 text-green-500" />
                                            ) : (
                                                <span className="text-xs text-slate-400">skipped</span>
                                            )}
                                        </div>
                                    </div>
                                ))}

                                {/* Processing recommendation */}
                                <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
                                    <strong>Smart Processing:</strong> {tabAnalysis.efficiency?.process_rows || 0} rows from {tabAnalysis.efficiency?.process_tabs || 0} detail tabs.
                                    {tabAnalysis.efficiency?.skip_rows > 0 && (
                                        <span> Skipped {tabAnalysis.efficiency.skip_rows} rows from summary/prior year tabs.</span>
                                    )}
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}
        </div>
    );
}

export { Import };
export default Import;
