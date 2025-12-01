import React from 'react';
import { LayoutDashboard, FileInput, CheckSquare, Settings, LogOut, Sparkles } from 'lucide-react';
import { cn } from '../lib/utils';

const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', id: 'dashboard' },
    { icon: FileInput, label: 'Import Data', id: 'import' },
    { icon: Sparkles, label: 'Data Cleanup', id: 'cleanup', badge: 'NEW' },
    { icon: CheckSquare, label: 'Review & Approve', id: 'review' },
    { icon: Settings, label: 'Settings', id: 'settings' },
];

export function Sidebar({ activeTab, setActiveTab }) {
    return (
        <div className="w-64 bg-card border-r border-border h-screen flex flex-col">
            <div className="p-6 border-b border-border">
                <h1 className="text-xl font-bold text-primary flex items-center gap-2">
                    <span className="w-8 h-8 bg-primary text-primary-foreground rounded-lg flex items-center justify-center">FA</span>
                    CS Automator
                </h1>
            </div>

            <nav className="flex-1 p-4 space-y-2">
                {navItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = activeTab === item.id;
                    return (
                        <button
                            key={item.id}
                            onClick={() => setActiveTab(item.id)}
                            className={cn(
                                "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors text-sm font-medium",
                                isActive
                                    ? "bg-primary text-primary-foreground"
                                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                            )}
                        >
                            <Icon size={20} />
                            <span className="flex-1 text-left">{item.label}</span>
                            {item.badge && (
                                <span className={cn(
                                    "px-1.5 py-0.5 text-[10px] font-bold rounded",
                                    isActive
                                        ? "bg-primary-foreground/20 text-primary-foreground"
                                        : "bg-green-100 text-green-700"
                                )}>
                                    {item.badge}
                                </span>
                            )}
                        </button>
                    );
                })}
            </nav>

            <div className="p-4 border-t border-border">
                <button className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors text-sm font-medium">
                    <LogOut size={20} />
                    Logout
                </button>
            </div>
        </div>
    );
}

export default Sidebar;
