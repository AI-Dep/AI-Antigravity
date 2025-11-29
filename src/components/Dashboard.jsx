import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Activity, FileText, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';

export function Dashboard() {
    const [systemStatus, setSystemStatus] = useState("Checking...");
    const [isOnline, setIsOnline] = useState(false);

    const checkStatus = async () => {
        setSystemStatus("Connecting...");
        try {
            // In a real Electron app, you might use IPC, but HTTP is easier for the hybrid approach
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

    useEffect(() => {
        checkStatus();
        const interval = setInterval(checkStatus, 10000); // Poll every 10s
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Assets Processed</CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">1,284</div>
                        <p className="text-xs text-muted-foreground">+20.1% from last month</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Pending Reviews</CardTitle>
                        <FileText className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">12</div>
                        <p className="text-xs text-muted-foreground">Requires attention</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
                        <CheckCircle className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">98.5%</div>
                        <p className="text-xs text-muted-foreground">+2% improvement</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">System Status</CardTitle>
                        <AlertCircle className={isOnline ? "h-4 w-4 text-green-500" : "h-4 w-4 text-red-500"} />
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
                            <p className="text-sm text-muted-foreground">12 items waiting</p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
