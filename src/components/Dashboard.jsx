import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Activity, FileText, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';

export function Dashboard() {
    const [systemStatus, setSystemStatus] = useState("Checking...");
    const [isOnline, setIsOnline] = useState(false);
    const [stats, setStats] = useState({
        total: 0,
        errors: 0,
        needs_review: 0,
        high_confidence: 0,
        approved: 0,
        ready_for_export: false
    });

    const checkStatus = async () => {
        setSystemStatus("Connecting...");
        try {
            const response = await fetch('http://127.0.0.1:8000/check-facs');
            const data = await response.json();
            if (data.running) {
                setSystemStatus("Operational (FA CS Connected)");
                setIsOnline(true);
            } else {
                setSystemStatus("Backend Online (FA CS Not Found)");
                setIsOnline(true);
            }
        } catch (error) {
            setSystemStatus("Backend Offline");
            setIsOnline(false);
        }
    };

    const fetchStats = async () => {
        try {
            const response = await fetch('http://127.0.0.1:8000/stats');
            if (response.ok) {
                const data = await response.json();
                setStats(data);
            }
        } catch (error) {
            // Stats fetch failed, keep defaults
        }
    };

    useEffect(() => {
        checkStatus();
        fetchStats();
        const statusInterval = setInterval(checkStatus, 10000);
        const statsInterval = setInterval(fetchStats, 5000); // Update stats every 5s
        return () => {
            clearInterval(statusInterval);
            clearInterval(statsInterval);
        };
    }, []);

    return (
        <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
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
                <Card>
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
                        <CardTitle className="text-sm font-medium">System Status</CardTitle>
                        <CheckCircle className={isOnline ? "h-4 w-4 text-green-500" : "h-4 w-4 text-red-500"} />
                    </CardHeader>
                    <CardContent>
                        <div className={`text-lg font-bold ${isOnline ? "text-green-600" : "text-red-600"}`}>
                            {systemStatus}
                        </div>
                        <Button variant="ghost" size="sm" onClick={checkStatus} className="h-6 px-2 mt-1 text-xs">
                            <RefreshCw size={12} className="mr-1" /> Retry
                        </Button>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Recent Activity</CardTitle>
                        <CardDescription>
                            You processed 24 files this week.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {[1, 2, 3].map((i) => (
                                <div key={i} className="flex items-center">
                                    <div className="ml-4 space-y-1">
                                        <p className="text-sm font-medium leading-none">Client_Asset_Schedule_{i}.xlsx</p>
                                        <p className="text-sm text-muted-foreground">
                                            Processed at 10:00 AM
                                        </p>
                                    </div>
                                    <div className="ml-auto font-medium text-green-600">Completed</div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Quick Actions</CardTitle>
                        <CardDescription>
                            Common tasks
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-2">
                        <div className="p-4 border rounded-lg hover:bg-accent cursor-pointer transition-colors">
                            <p className="font-medium">Import New Schedule</p>
                            <p className="text-sm text-muted-foreground">Upload Excel file</p>
                        </div>
                        <div className="p-4 border rounded-lg hover:bg-accent cursor-pointer transition-colors">
                            <p className="font-medium">Review Pending Items</p>
                            <p className="text-sm text-muted-foreground">
                                {stats.needs_review + stats.errors} items need attention
                            </p>
                        </div>
                        <div className={`p-4 border rounded-lg transition-colors ${
                            stats.ready_for_export
                                ? 'bg-green-50 border-green-200 hover:bg-green-100 cursor-pointer'
                                : 'bg-gray-50 border-gray-200 cursor-not-allowed opacity-60'
                        }`}>
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
            </div>
        </div>
    );
}
