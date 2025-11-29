import React, { useState, useRef } from 'react';
import { Upload, FileSpreadsheet, AlertCircle, CheckCircle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import axios from 'axios';

export function Import({ onUploadSuccess }) {
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState(null);
    const fileInputRef = useRef(null);

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = () => {
        setIsDragging(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
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

        const formData = new FormData();
        formData.append('file', file);

        try {
            // Send to Python Backend
            const response = await axios.post('http://127.0.0.1:8000/upload', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });

            // Success! Pass data up to App
            onUploadSuccess(response.data);

        } catch (err) {
            console.error("Upload failed:", err);
            // Show detailed error message from backend if available
            if (err.response && err.response.data && err.response.data.detail) {
                setError(`Error: ${err.response.data.detail}`);
            } else if (err.message) {
                setError(`Failed to process file: ${err.message}`);
            } else {
                setError("Failed to process file. Is the backend running?");
            }
        } finally {
            setIsUploading(false);
        }
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
                            <AlertCircle className="w-5 h-5 mr-2" />
                            {error}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
