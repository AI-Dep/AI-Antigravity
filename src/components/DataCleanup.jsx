import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Button } from './ui/button';
import {
    Sparkles, Calendar, Hash, FileText, AlertTriangle, CheckCircle2,
    Wand2, RefreshCw, Download, ChevronDown, ChevronUp, Loader2,
    AlertCircle, Clock, Type, Calculator
} from 'lucide-react';
import { cn } from '../lib/utils';
import { apiGet, apiPost } from '../lib/api.client';

/**
 * Data Cleanup Module - Automatically fixes common data quality issues
 *
 * Features:
 * - Auto-fix bad dates (e.g., "2/30/24", "13/15/2024")
 * - Auto-fix negative formatting (e.g., "4,129.66-" → "-4,129.66")
 * - Auto-fix OCR/text scraping errors
 * - Auto-fill missing In-Service dates from acquisition date
 * - Header detection for any format
 */
export function DataCleanup({ setActiveTab }) {
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [fixing, setFixing] = useState(null);
    const [issues, setIssues] = useState(null);
    const [stats, setStats] = useState({ total: 0 });
    const [expandedCategories, setExpandedCategories] = useState({});

    // Fetch current data issues
    const analyzeData = useCallback(async () => {
        setAnalyzing(true);
        try {
            const data = await apiGet('/cleanup/analyze');
            setIssues(data.issues || {});
            setStats(data.stats || { total: 0 });
        } catch (error) {
            console.error('Failed to analyze data:', error);
            // Initialize with empty state if API not ready
            setIssues({});
        } finally {
            setAnalyzing(false);
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        analyzeData();
    }, [analyzeData]);

    // Apply auto-fix for a category
    const applyFix = async (category) => {
        setFixing(category);
        try {
            const result = await apiPost('/cleanup/fix', { category });
            // Re-analyze after fix
            await analyzeData();
            return result;
        } catch (error) {
            console.error(`Failed to fix ${category}:`, error);
        } finally {
            setFixing(null);
        }
    };

    // Apply all fixes
    const applyAllFixes = async () => {
        setFixing('all');
        try {
            await apiPost('/cleanup/fix-all');
            await analyzeData();
        } catch (error) {
            console.error('Failed to apply all fixes:', error);
        } finally {
            setFixing(null);
        }
    };

    // Toggle category expansion
    const toggleCategory = (category) => {
        setExpandedCategories(prev => ({
            ...prev,
            [category]: !prev[category]
        }));
    };

    // Issue categories with icons and descriptions
    const issueCategories = [
        {
            id: 'invalid_dates',
            icon: Calendar,
            title: 'Invalid Dates',
            description: 'Dates that don\'t exist (e.g., Feb 30) or have wrong format',
            color: 'text-red-500',
            bgColor: 'bg-red-50',
            fixLabel: 'Auto-Fix Dates'
        },
        {
            id: 'negative_format',
            icon: Hash,
            title: 'Negative Number Format',
            description: 'Numbers with trailing minus (e.g., "4,129.66-")',
            color: 'text-orange-500',
            bgColor: 'bg-orange-50',
            fixLabel: 'Fix Formatting'
        },
        {
            id: 'missing_dates',
            icon: Clock,
            title: 'Missing In-Service Dates',
            description: 'Can be auto-filled from acquisition date',
            color: 'text-yellow-500',
            bgColor: 'bg-yellow-50',
            fixLabel: 'Auto-Fill Dates'
        },
        {
            id: 'ocr_errors',
            icon: Type,
            title: 'OCR/Text Errors',
            description: 'Common scanning mistakes (O vs 0, l vs 1)',
            color: 'text-purple-500',
            bgColor: 'bg-purple-50',
            fixLabel: 'Fix Text Errors'
        },
        {
            id: 'cost_format',
            icon: Calculator,
            title: 'Cost Format Issues',
            description: 'Currency symbols, commas, or invalid characters in costs',
            color: 'text-blue-500',
            bgColor: 'bg-blue-50',
            fixLabel: 'Clean Costs'
        }
    ];

    // Count total issues
    const totalIssues = issues ? Object.values(issues).reduce((sum, arr) => sum + (arr?.length || 0), 0) : 0;
    const hasIssues = totalIssues > 0;

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">Analyzing data quality...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
                        <Sparkles className="h-6 w-6 text-yellow-500" />
                        Data Cleanup
                    </h2>
                    <p className="text-muted-foreground">
                        Automatically fix common data quality issues before review
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button
                        variant="outline"
                        onClick={analyzeData}
                        disabled={analyzing}
                    >
                        <RefreshCw className={cn("h-4 w-4 mr-2", analyzing && "animate-spin")} />
                        Re-Analyze
                    </Button>
                    {hasIssues && (
                        <Button
                            onClick={applyAllFixes}
                            disabled={fixing !== null}
                            className="bg-green-600 hover:bg-green-700"
                        >
                            <Wand2 className="h-4 w-4 mr-2" />
                            Fix All Issues ({totalIssues})
                        </Button>
                    )}
                </div>
            </div>

            {/* Summary Card */}
            <Card>
                <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            {hasIssues ? (
                                <div className="h-12 w-12 rounded-full bg-yellow-100 flex items-center justify-center">
                                    <AlertTriangle className="h-6 w-6 text-yellow-600" />
                                </div>
                            ) : (
                                <div className="h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                                    <CheckCircle2 className="h-6 w-6 text-green-600" />
                                </div>
                            )}
                            <div>
                                <h3 className="text-lg font-semibold">
                                    {hasIssues
                                        ? `${totalIssues} Issues Found`
                                        : 'Data is Clean!'
                                    }
                                </h3>
                                <p className="text-sm text-muted-foreground">
                                    {stats.total} assets analyzed
                                    {hasIssues && ' • Click "Fix All" or fix individual categories'}
                                </p>
                            </div>
                        </div>
                        {!hasIssues && stats.total > 0 && (
                            <Button onClick={() => setActiveTab && setActiveTab('review')}>
                                Proceed to Review
                            </Button>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Issue Categories */}
            <div className="grid gap-4">
                {issueCategories.map((category) => {
                    const categoryIssues = issues?.[category.id] || [];
                    const count = categoryIssues.length;
                    const isExpanded = expandedCategories[category.id];
                    const Icon = category.icon;
                    const isFixing = fixing === category.id || fixing === 'all';

                    return (
                        <Card key={category.id} className={cn(count > 0 && category.bgColor)}>
                            <CardHeader className="pb-2">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className={cn(
                                            "h-10 w-10 rounded-lg flex items-center justify-center",
                                            count > 0 ? category.bgColor : "bg-slate-100"
                                        )}>
                                            <Icon className={cn("h-5 w-5", count > 0 ? category.color : "text-slate-400")} />
                                        </div>
                                        <div>
                                            <CardTitle className="text-base flex items-center gap-2">
                                                {category.title}
                                                {count > 0 && (
                                                    <span className={cn(
                                                        "px-2 py-0.5 text-xs font-bold rounded-full",
                                                        category.bgColor, category.color
                                                    )}>
                                                        {count}
                                                    </span>
                                                )}
                                            </CardTitle>
                                            <CardDescription>{category.description}</CardDescription>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {count > 0 && (
                                            <>
                                                <Button
                                                    size="sm"
                                                    onClick={() => applyFix(category.id)}
                                                    disabled={isFixing}
                                                    className="h-8"
                                                >
                                                    {isFixing ? (
                                                        <Loader2 className="h-4 w-4 animate-spin" />
                                                    ) : (
                                                        <>
                                                            <Wand2 className="h-3 w-3 mr-1" />
                                                            {category.fixLabel}
                                                        </>
                                                    )}
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => toggleCategory(category.id)}
                                                    className="h-8 w-8 p-0"
                                                >
                                                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                                </Button>
                                            </>
                                        )}
                                        {count === 0 && (
                                            <span className="text-sm text-green-600 flex items-center gap-1">
                                                <CheckCircle2 className="h-4 w-4" />
                                                Clean
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </CardHeader>

                            {/* Expanded Details */}
                            {isExpanded && count > 0 && (
                                <CardContent className="pt-0">
                                    <div className="mt-3 border rounded-lg overflow-hidden">
                                        <table className="w-full text-sm">
                                            <thead className="bg-slate-50">
                                                <tr>
                                                    <th className="text-left px-3 py-2 font-medium">Asset</th>
                                                    <th className="text-left px-3 py-2 font-medium">Issue</th>
                                                    <th className="text-left px-3 py-2 font-medium">Current Value</th>
                                                    <th className="text-left px-3 py-2 font-medium">Suggested Fix</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y">
                                                {categoryIssues.slice(0, 10).map((issue, idx) => (
                                                    <tr key={idx} className="hover:bg-slate-50/50">
                                                        <td className="px-3 py-2 font-mono text-xs">
                                                            {issue.asset_id || `Row ${issue.row}`}
                                                        </td>
                                                        <td className="px-3 py-2">{issue.field}</td>
                                                        <td className="px-3 py-2 text-red-600 font-mono text-xs">
                                                            {issue.current_value}
                                                        </td>
                                                        <td className="px-3 py-2 text-green-600 font-mono text-xs">
                                                            {issue.suggested_fix || 'Auto-fix available'}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                        {categoryIssues.length > 10 && (
                                            <div className="px-3 py-2 text-xs text-muted-foreground bg-slate-50 text-center">
                                                And {categoryIssues.length - 10} more...
                                            </div>
                                        )}
                                    </div>
                                </CardContent>
                            )}
                        </Card>
                    );
                })}
            </div>

            {/* Tips Card */}
            <Card className="bg-blue-50 border-blue-200">
                <CardContent className="pt-6">
                    <div className="flex gap-3">
                        <AlertCircle className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
                        <div>
                            <h4 className="font-medium text-blue-900">Pro Tips</h4>
                            <ul className="mt-1 text-sm text-blue-700 space-y-1">
                                <li>• Auto-fill uses acquisition date + 30 days for missing in-service dates</li>
                                <li>• Invalid dates like Feb 30 are corrected to the last valid day of the month</li>
                                <li>• OCR fixes include: O→0, l→1, S→5, B→8 in numeric fields</li>
                                <li>• All fixes are logged and can be reviewed in the audit trail</li>
                            </ul>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

export default DataCleanup;
