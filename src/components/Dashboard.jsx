import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import {
    Activity, FileText, CheckCircle, AlertCircle, RefreshCw, Monitor, MonitorOff,
    TrendingUp, Scale, Brain, ChevronDown, ChevronUp, Cpu, Database, Loader2,
    Clock, Zap, Copy
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { cn } from '../lib/utils';
import { apiGet, apiPost } from '../lib/api.client';

function Dashboard() {
    const navigate = useNavigate();
    const [systemStatus, setSystemStatus] = useState("Checking...");
    const [isOnline, setIsOnline] = useState(false);
    const [initialLoading, setInitialLoading] = useState(true); // Show loading on first render
    const mountedRef = useRef(true); // Track component mount state
    const [facsConnected, setFacsConnected] = useState(false);
    const [isRemoteMode, setIsRemoteMode] = useState(true);
    const [stats, setStats] = useState({
        total: 0,
        errors: 0,
        needs_review: 0,
        high_confidence: 0,
        approved: 0,
        ready_for_export: false
    });

    // New state for enhanced features
    const [quality, setQuality] = useState({ grade: '-', score: 0, checks: [], cross_sheet_duplicates: [] });
    const [rollforward, setRollforward] = useState({ is_balanced: true, expected_ending: 0 });
    const [projection, setProjection] = useState({ years: [], depreciation: [], current_year: 0 });
    const [systemInfo, setSystemInfo] = useState({ ai: {}, memory: {}, rules: {} });
    const [sessionMetrics, setSessionMetrics] = useState({
        import_duration_ms: 0,
        total_assets_imported: 0,
        high_confidence_count: 0,
        assets_needing_review: 0,
        file_name: null
    });

    // Expandable sections state
    const [showQualityDetails, setShowQualityDetails] = useState(false);
    const [showRollforwardDetails, setShowRollforwardDetails] = useState(false);
    const [showProjectionDetails, setShowProjectionDetails] = useState(false);

    const checkStatus = useCallback(async () => {
        if (!mountedRef.current) return;
        setSystemStatus("Connecting...");
        try {
            const data = await apiGet('/check-facs');
            if (!mountedRef.current) return;
            setIsRemoteMode(data.remote_mode || false);
            setFacsConnected(data.running || false);

            if (data.running) {
                setSystemStatus(data.remote_mode ? "Remote FA CS Connected" : "FA CS Connected");
                setIsOnline(true);
            } else {
                setSystemStatus(data.remote_mode ? "Backend Online (Confirm FA CS)" : "Backend Online (FA CS Not Found)");
                setIsOnline(true);
            }
        } catch (error) {
            if (!mountedRef.current) return;
            setSystemStatus("Backend Offline");
            setIsOnline(false);
        }
    }, []);

    const confirmFacsConnection = async () => {
        try {
            await apiPost('/facs/confirm-connected');
            if (!mountedRef.current) return;
            setFacsConnected(true);
            setSystemStatus("Remote FA CS Connected");
        } catch (error) {
            console.error("Failed to confirm FA CS connection");
        }
    };

    const disconnectFacs = async () => {
        try {
            await apiPost('/facs/disconnect');
            if (!mountedRef.current) return;
            setFacsConnected(false);
            setSystemStatus("Backend Online (Confirm FA CS)");
        } catch (error) {
            console.error("Failed to disconnect FA CS");
        }
    };

    const fetchStats = useCallback(async () => {
        try {
            const data = await apiGet('/stats');
            if (mountedRef.current) {
                setStats(data);
                // Extract session metrics for ROI display
                if (data.session_metrics) {
                    setSessionMetrics(data.session_metrics);
                }
            }
        } catch (error) {
            // Stats fetch failed, keep defaults
        }
    }, []);

    const fetchQuality = useCallback(async () => {
        try {
            const data = await apiGet('/quality');
            if (mountedRef.current) setQuality(data);
        } catch (error) {
            // Quality fetch failed
        }
    }, []);

    const fetchRollforward = useCallback(async () => {
        try {
            const data = await apiGet('/rollforward');
            if (mountedRef.current) setRollforward(data);
        } catch (error) {
            // Rollforward fetch failed
        }
    }, []);

    const fetchProjection = useCallback(async () => {
        try {
            const data = await apiGet('/projection');
            if (mountedRef.current) setProjection(data);
        } catch (error) {
            // Projection fetch failed
        }
    }, []);

    const fetchSystemInfo = useCallback(async () => {
        try {
            const data = await apiGet('/system-status');
            if (mountedRef.current) setSystemInfo(data);
        } catch (error) {
            // System info fetch failed
        }
    }, []);

    useEffect(() => {
        mountedRef.current = true;

        // Initial data load - Session ID is generated client-side in api.client.js
        // so all requests automatically use the same session (no race condition)
        const loadInitialData = async () => {
            // Load all data in parallel - session ID is already available client-side
            await Promise.all([
                checkStatus(),
                fetchStats(),
                fetchQuality(),
                fetchRollforward(),
                fetchProjection(),
                fetchSystemInfo()
            ]);
            if (mountedRef.current) {
                setInitialLoading(false);
            }
        };

        loadInitialData();

        // Polling intervals
        const statusInterval = setInterval(checkStatus, 10000);
        const statsInterval = setInterval(() => {
            // Only poll data endpoints if backend is online
            if (mountedRef.current) {
                fetchStats();
                fetchQuality();
                fetchRollforward();
                fetchProjection();
            }
        }, 5000);

        return () => {
            mountedRef.current = false;
            clearInterval(statusInterval);
            clearInterval(statsInterval);
        };
    }, [checkStatus, fetchStats, fetchQuality, fetchRollforward, fetchProjection, fetchSystemInfo]);

    // Get grade color
    const getGradeColor = (grade) => {
        const colors = {
            'A': 'text-green-600 bg-green-100 border-green-200',
            'B': 'text-blue-600 bg-blue-100 border-blue-200',
            'C': 'text-yellow-600 bg-yellow-100 border-yellow-200',
            'D': 'text-orange-600 bg-orange-100 border-orange-200',
            'F': 'text-red-600 bg-red-100 border-red-200',
            '-': 'text-slate-400 bg-slate-100 border-slate-200',
        };
        return colors[grade] || colors['-'];
    };

    // Show loading spinner during initial load
    if (initialLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">Loading dashboard...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Main Stats Row */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card
                    className="cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => navigate('/review')}
                >
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Assets</CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.total}</div>
                        <p className="text-xs text-muted-foreground">
                            {stats.approved} approved, {stats.high_confidence} high confidence
                        </p>
                    </CardContent>
                </Card>
                <Card
                    className="cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => navigate('/review')}
                >
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Needs Review</CardTitle>
                        <FileText className={`h-4 w-4 ${stats.needs_review > 0 ? 'text-yellow-500' : 'text-muted-foreground'}`} />
                    </CardHeader>
                    <CardContent>
                        <div className={`text-2xl font-bold ${stats.needs_review > 0 ? 'text-yellow-600' : ''}`}>
                            {stats.needs_review}
                        </div>
                        <p className="text-xs text-muted-foreground">Low confidence items</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Errors</CardTitle>
                        <AlertCircle className={`h-4 w-4 ${stats.errors > 0 ? 'text-red-500' : 'text-green-500'}`} />
                    </CardHeader>
                    <CardContent>
                        <div className={`text-2xl font-bold ${stats.errors > 0 ? 'text-red-600' : 'text-green-600'}`}>
                            {stats.errors}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {stats.errors > 0 ? 'Must fix before export' : 'Ready to proceed'}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">FA CS Connection</CardTitle>
                        {facsConnected ?
                            <Monitor className="h-4 w-4 text-green-500" /> :
                            isOnline ?
                                <Monitor className="h-4 w-4 text-green-400" /> :
                                <MonitorOff className="h-4 w-4 text-red-500" />
                        }
                    </CardHeader>
                    <CardContent>
                        <div className={`text-sm font-bold ${facsConnected ? "text-green-600" : isOnline ? "text-green-500" : "text-red-600"}`}>
                            {systemStatus}
                        </div>
                        {isRemoteMode && isOnline && (
                            <div className="mt-2 flex gap-1">
                                {!facsConnected ? (
                                    <Button
                                        variant="default"
                                        size="sm"
                                        onClick={confirmFacsConnection}
                                        className="h-7 px-3 text-xs bg-blue-600 hover:bg-blue-700"
                                    >
                                        <Monitor size={12} className="mr-1" /> I'm Connected to FA CS
                                    </Button>
                                ) : (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={disconnectFacs}
                                        className="h-7 px-3 text-xs"
                                    >
                                        <MonitorOff size={12} className="mr-1" /> Disconnect
                                    </Button>
                                )}
                            </div>
                        )}
                        {!isOnline && (
                            <Button variant="ghost" size="sm" onClick={checkStatus} className="h-6 px-2 mt-1 text-xs">
                                <RefreshCw size={12} className="mr-1" /> Retry
                            </Button>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Data Quality & Insights Row */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {/* Data Quality Grade */}
                <Card className="overflow-hidden">
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <CardTitle className="text-sm font-medium">Data Quality</CardTitle>
                            <button
                                onClick={() => setShowQualityDetails(!showQualityDetails)}
                                className="text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {showQualityDetails ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                            </button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-4">
                            <div className={cn(
                                "text-4xl font-bold w-16 h-16 rounded-lg flex items-center justify-center border-2",
                                getGradeColor(quality.grade)
                            )}>
                                {quality.grade}
                            </div>
                            <div className="flex-1">
                                <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                                    <div
                                        className={cn(
                                            "h-full transition-all duration-500",
                                            quality.score >= 80 ? "bg-green-500" :
                                                quality.score >= 60 ? "bg-yellow-500" : "bg-red-500"
                                        )}
                                        style={{ width: `${quality.score}%` }}
                                    />
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {quality.score}% - {quality.is_export_ready ? 'Export Ready' : 'Review Needed'}
                                </p>
                            </div>
                        </div>

                        {/* Expandable Details */}
                        {showQualityDetails && quality.checks?.length > 0 && (
                            <div className="mt-4 pt-4 border-t space-y-2">
                                {quality.checks.map((check, idx) => (
                                    <div key={idx} className="flex items-center justify-between text-xs">
                                        <span className="flex items-center gap-2">
                                            {check.passed ?
                                                <CheckCircle className="w-3 h-3 text-green-500" /> :
                                                <AlertCircle className="w-3 h-3 text-red-500" />
                                            }
                                            {check.name}
                                        </span>
                                        <span className={check.passed ? "text-green-600" : "text-red-600"}>
                                            {check.score.toFixed(0)}%
                                        </span>
                                    </div>
                                ))}

                                {/* Cross-sheet duplicates warning */}
                                {quality.cross_sheet_duplicates?.length > 0 && (
                                    <div className="mt-3 pt-3 border-t">
                                        <div className="flex items-center gap-2 text-xs text-orange-600 font-medium mb-2">
                                            <Copy className="w-3 h-3" />
                                            {quality.cross_sheet_duplicates.length} Cross-Sheet Duplicate(s)
                                        </div>
                                        <div className="space-y-1">
                                            {quality.cross_sheet_duplicates.slice(0, 3).map((dup, idx) => (
                                                <div key={idx} className="text-xs text-muted-foreground bg-orange-50 p-1.5 rounded">
                                                    <span className="font-mono">{dup.asset_id}</span>
                                                    <span className="mx-1">in</span>
                                                    <span className="italic">{dup.sheets.join(', ')}</span>
                                                </div>
                                            ))}
                                            {quality.cross_sheet_duplicates.length > 3 && (
                                                <div className="text-xs text-muted-foreground">
                                                    + {quality.cross_sheet_duplicates.length - 3} more...
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Rollforward Reconciliation */}
                <Card className="overflow-hidden">
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <CardTitle className="text-sm font-medium">Rollforward Status</CardTitle>
                            <button
                                onClick={() => setShowRollforwardDetails(!showRollforwardDetails)}
                                className="text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {showRollforwardDetails ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                            </button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-4">
                            <Scale className={cn(
                                "w-10 h-10",
                                rollforward.is_balanced ? "text-green-500" : "text-red-500"
                            )} />
                            <div>
                                <div className={cn(
                                    "text-lg font-bold",
                                    rollforward.is_balanced ? "text-green-600" : "text-red-600"
                                )}>
                                    {rollforward.status_label || (rollforward.is_balanced ? 'Balanced' : 'Out of Balance')}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    Ending: ${rollforward.expected_ending?.toLocaleString() || 0}
                                </p>
                            </div>
                        </div>

                        {/* Expandable Details */}
                        {showRollforwardDetails && (
                            <div className="mt-4 pt-4 border-t text-xs space-y-1">
                                <div className="flex justify-between">
                                    <span>Beginning Balance:</span>
                                    <span className="font-mono">${rollforward.beginning_balance?.toLocaleString() || 0}</span>
                                </div>
                                <div className="flex justify-between text-green-600">
                                    <span>+ Additions:</span>
                                    <span className="font-mono">${rollforward.additions?.toLocaleString() || 0}</span>
                                </div>
                                {rollforward.de_minimis_count > 0 && (
                                    <div className="flex justify-between text-emerald-600 text-[10px] pl-2" title="Expensed via De Minimis Safe Harbor - NOT capitalized">
                                        <span className="italic">({rollforward.de_minimis_count} items expensed: ${rollforward.de_minimis_expensed?.toLocaleString() || 0})</span>
                                    </div>
                                )}
                                <div className="flex justify-between text-red-600">
                                    <span>- Disposals:</span>
                                    <span className="font-mono">(${rollforward.disposals?.toLocaleString() || 0})</span>
                                </div>
                                {rollforward.transfers_in > 0 && (
                                    <div className="flex justify-between">
                                        <span>+ Transfers In:</span>
                                        <span className="font-mono">${rollforward.transfers_in?.toLocaleString() || 0}</span>
                                    </div>
                                )}
                                {rollforward.transfers_out > 0 && (
                                    <div className="flex justify-between">
                                        <span>- Transfers Out:</span>
                                        <span className="font-mono">(${rollforward.transfers_out?.toLocaleString() || 0})</span>
                                    </div>
                                )}
                                <div className="flex justify-between font-bold pt-1 border-t">
                                    <span>= Ending Balance:</span>
                                    <span className="font-mono">${rollforward.expected_ending?.toLocaleString() || 0}</span>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Depreciation Projection */}
                <Card className="overflow-hidden">
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <CardTitle className="text-sm font-medium">10-Year Projection</CardTitle>
                            <button
                                onClick={() => setShowProjectionDetails(!showProjectionDetails)}
                                className="text-muted-foreground hover:text-foreground transition-colors"
                            >
                                {showProjectionDetails ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                            </button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-4">
                            <TrendingUp className="w-10 h-10 text-blue-500" />
                            <div>
                                <div className="text-lg font-bold text-blue-600">
                                    ${projection.current_year?.toLocaleString() || 0}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    Current year depreciation
                                </p>
                            </div>
                        </div>

                        {/* Mini Chart */}
                        {projection.depreciation?.length > 0 && (
                            <div className="mt-3 flex items-end gap-1 h-12">
                                {projection.depreciation.slice(0, 10).map((dep, idx) => {
                                    const maxDep = Math.max(...projection.depreciation);
                                    const height = maxDep > 0 ? (dep / maxDep) * 100 : 0;
                                    return (
                                        <div
                                            key={idx}
                                            className="flex-1 bg-blue-200 hover:bg-blue-400 transition-colors rounded-t"
                                            style={{ height: `${Math.max(height, 4)}%` }}
                                            title={`${projection.years[idx]}: $${dep.toLocaleString()}`}
                                        />
                                    );
                                })}
                            </div>
                        )}

                        {/* Expandable Details */}
                        {showProjectionDetails && projection.years?.length > 0 && (
                            <div className="mt-4 pt-4 border-t text-xs">
                                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                                    {projection.years.slice(0, 10).map((year, idx) => (
                                        <div key={year} className="flex justify-between">
                                            <span>{year}:</span>
                                            <span className="font-mono">${projection.depreciation[idx]?.toLocaleString() || 0}</span>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex justify-between font-bold mt-2 pt-2 border-t">
                                    <span>10-Year Total:</span>
                                    <span className="font-mono">${projection.total_10_year?.toLocaleString() || 0}</span>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Session Metrics - ROI Demonstration */}
                <Card className="overflow-hidden">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium">Processing Summary</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-4">
                            <div className={cn(
                                "w-12 h-12 rounded-lg flex items-center justify-center",
                                sessionMetrics.import_duration_ms > 0
                                    ? "bg-green-100 text-green-600"
                                    : "bg-slate-100 text-slate-400"
                            )}>
                                <Zap className="w-6 h-6" />
                            </div>
                            <div className="flex-1">
                                {sessionMetrics.import_duration_ms > 0 ? (
                                    <>
                                        <div className="text-lg font-bold text-green-600">
                                            {(sessionMetrics.import_duration_ms / 1000).toFixed(1)}s
                                        </div>
                                        <p className="text-xs text-muted-foreground">
                                            {sessionMetrics.total_assets_imported} assets classified
                                        </p>
                                    </>
                                ) : (
                                    <>
                                        <div className="text-sm font-medium text-slate-500">
                                            No import yet
                                        </div>
                                        <p className="text-xs text-muted-foreground">
                                            Upload a file to see metrics
                                        </p>
                                    </>
                                )}
                            </div>
                        </div>

                        {/* Metrics breakdown */}
                        {sessionMetrics.import_duration_ms > 0 && (
                            <div className="mt-4 pt-3 border-t space-y-2 text-xs">
                                <div className="flex justify-between items-center">
                                    <span className="flex items-center gap-1">
                                        <CheckCircle className="w-3 h-3 text-green-500" />
                                        High Confidence
                                    </span>
                                    <span className="font-mono text-green-600">
                                        {sessionMetrics.high_confidence_count || 0}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="flex items-center gap-1">
                                        <AlertCircle className="w-3 h-3 text-yellow-500" />
                                        Needs Review
                                    </span>
                                    <span className="font-mono text-yellow-600">
                                        {sessionMetrics.assets_needing_review || 0}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center pt-2 border-t">
                                    <span className="flex items-center gap-1">
                                        <Clock className="w-3 h-3 text-blue-500" />
                                        Est. Time Saved
                                    </span>
                                    <span className="font-mono font-bold text-blue-600">
                                        ~{Math.max(1, Math.round(sessionMetrics.total_assets_imported * 2 / 60))}h
                                    </span>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Bottom Row: Activity & System Status */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Quick Actions</CardTitle>
                        <CardDescription>Common tasks for your workflow</CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-2">
                        <div
                            className="p-4 border rounded-lg hover:bg-accent cursor-pointer transition-colors"
                            onClick={() => navigate('/import')}
                        >
                            <p className="font-medium">Import New Schedule</p>
                            <p className="text-sm text-muted-foreground">Upload Excel file for AI classification</p>
                        </div>
                        <div
                            className="p-4 border rounded-lg hover:bg-accent cursor-pointer transition-colors"
                            onClick={() => navigate('/review')}
                        >
                            <p className="font-medium">Review Pending Items</p>
                            <p className="text-sm text-muted-foreground">
                                {stats.needs_review + stats.errors} items need attention
                            </p>
                        </div>
                        <div
                            className={`p-4 border rounded-lg transition-colors ${stats.ready_for_export
                                ? 'bg-green-50 border-green-200 hover:bg-green-100 cursor-pointer'
                                : 'bg-gray-50 border-gray-200 cursor-not-allowed opacity-60'
                            }`}
                            onClick={() => stats.ready_for_export && navigate('/review')}
                        >
                            <p className="font-medium">
                                {stats.ready_for_export ? 'Export to FA CS' : 'Export Not Ready'}
                            </p>
                            <p className="text-sm text-muted-foreground">
                                {stats.ready_for_export
                                    ? `${stats.total} assets ready`
                                    : stats.errors > 0
                                        ? `Fix ${stats.errors} error(s) first`
                                        : 'Upload assets first'
                                }
                            </p>
                        </div>
                    </CardContent>
                </Card>

                {/* System Status */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>System Status</CardTitle>
                        <CardDescription>Classification engine health</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50">
                            <div className="flex items-center gap-2">
                                <Cpu className={cn(
                                    "w-4 h-4",
                                    systemInfo.ai?.available ? "text-green-500" : "text-yellow-500"
                                )} />
                                <span className="text-sm">AI Classification</span>
                            </div>
                            <span className={cn(
                                "text-xs px-2 py-1 rounded",
                                systemInfo.ai?.available
                                    ? "bg-green-100 text-green-700"
                                    : "bg-yellow-100 text-yellow-700"
                            )}>
                                {systemInfo.ai?.status || "Unknown"}
                            </span>
                        </div>

                        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50">
                            <div className="flex items-center gap-2">
                                <Brain className="w-4 h-4 text-purple-500" />
                                <span className="text-sm">Memory Engine</span>
                            </div>
                            <span className="text-xs px-2 py-1 rounded bg-purple-100 text-purple-700">
                                {systemInfo.memory?.patterns_learned || 0} patterns
                            </span>
                        </div>

                        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50">
                            <div className="flex items-center gap-2">
                                <Database className="w-4 h-4 text-blue-500" />
                                <span className="text-sm">Classification Rules</span>
                            </div>
                            <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-700">
                                {systemInfo.rules?.count || 0} rules
                            </span>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

export { Dashboard };
export default Dashboard;
