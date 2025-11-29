import React from 'react';
import { Bell, User } from 'lucide-react';

export function Header({ title }) {
    return (
        <header className="h-16 border-b border-border bg-card flex items-center justify-between px-6">
            <h2 className="text-lg font-semibold text-foreground">{title}</h2>

            <div className="flex items-center gap-4">
                <button className="p-2 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent transition-colors">
                    <Bell size={20} />
                </button>
                <div className="flex items-center gap-3 pl-4 border-l border-border">
                    <div className="text-right hidden sm:block">
                        <p className="text-sm font-medium text-foreground">John Doe</p>
                        <p className="text-xs text-muted-foreground">Senior CPA</p>
                    </div>
                    <div className="w-10 h-10 bg-secondary rounded-full flex items-center justify-center text-secondary-foreground">
                        <User size={20} />
                    </div>
                </div>
            </div>
        </header>
    );
}

export default Header;
