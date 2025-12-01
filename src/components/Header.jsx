import React, { useState, useEffect, useRef } from 'react';
import { Bell, User, X, Edit2, Check } from 'lucide-react';

// Helper to get/set profile from localStorage
const getStoredProfile = () => {
    try {
        const stored = localStorage.getItem('userProfile');
        return stored ? JSON.parse(stored) : { name: 'John Doe', title: 'Senior CPA' };
    } catch {
        return { name: 'John Doe', title: 'Senior CPA' };
    }
};

const setStoredProfile = (profile) => {
    try {
        localStorage.setItem('userProfile', JSON.stringify(profile));
    } catch (e) {
        // localStorage may be unavailable (incognito) or full
        console.warn('Failed to save profile to localStorage:', e);
    }
};

export function Header({ title }) {
    // Notification state
    const [showNotifications, setShowNotifications] = useState(false);
    const [notifications, setNotifications] = useState([
        // Sample notifications - in production these would come from an API
    ]);
    const notificationRef = useRef(null);

    // Profile editing state
    const [profile, setProfile] = useState(getStoredProfile);
    const [showProfileEdit, setShowProfileEdit] = useState(false);
    const [editName, setEditName] = useState(profile.name);
    const [editTitle, setEditTitle] = useState(profile.title);
    const profileRef = useRef(null);

    // Close dropdowns when clicking outside
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (notificationRef.current && !notificationRef.current.contains(event.target)) {
                setShowNotifications(false);
            }
            if (profileRef.current && !profileRef.current.contains(event.target)) {
                setShowProfileEdit(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Save profile changes
    const handleSaveProfile = () => {
        const newProfile = { name: editName || 'User', title: editTitle || 'Staff' };
        setProfile(newProfile);
        setStoredProfile(newProfile);
        setShowProfileEdit(false);
    };

    // Clear a notification
    const clearNotification = (id) => {
        setNotifications(prev => prev.filter(n => n.id !== id));
    };

    return (
        <header className="h-16 border-b border-border bg-card flex items-center justify-between px-6">
            <h2 className="text-lg font-semibold text-foreground">{title}</h2>

            <div className="flex items-center gap-4">
                {/* Notification Bell */}
                <div className="relative" ref={notificationRef}>
                    <button
                        onClick={() => setShowNotifications(!showNotifications)}
                        className="p-2 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent transition-colors relative"
                    >
                        <Bell size={20} />
                        {notifications.length > 0 && (
                            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
                        )}
                    </button>

                    {/* Notification Dropdown */}
                    {showNotifications && (
                        <div className="absolute right-0 top-full mt-2 w-80 bg-card border border-border rounded-lg shadow-lg z-50">
                            <div className="p-3 border-b border-border">
                                <h3 className="font-semibold text-sm text-foreground">Notifications</h3>
                            </div>
                            <div className="max-h-64 overflow-y-auto">
                                {notifications.length === 0 ? (
                                    <div className="p-4 text-center text-muted-foreground text-sm">
                                        <Bell className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                        No new notifications
                                    </div>
                                ) : (
                                    notifications.map(notif => (
                                        <div key={notif.id} className="p-3 border-b border-border last:border-0 hover:bg-accent/50">
                                            <div className="flex justify-between items-start">
                                                <div className="flex-1">
                                                    <p className="text-sm font-medium text-foreground">{notif.title}</p>
                                                    <p className="text-xs text-muted-foreground mt-1">{notif.message}</p>
                                                </div>
                                                <button
                                                    onClick={() => clearNotification(notif.id)}
                                                    className="p-1 hover:bg-accent rounded"
                                                >
                                                    <X size={14} className="text-muted-foreground" />
                                                </button>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* User Profile */}
                <div className="relative" ref={profileRef}>
                    <button
                        onClick={() => {
                            setShowProfileEdit(!showProfileEdit);
                            setEditName(profile.name);
                            setEditTitle(profile.title);
                        }}
                        className="flex items-center gap-3 pl-4 border-l border-border hover:bg-accent/50 rounded-r-lg pr-2 py-1 transition-colors"
                    >
                        <div className="text-right hidden sm:block">
                            <p className="text-sm font-medium text-foreground">{profile.name}</p>
                            <p className="text-xs text-muted-foreground">{profile.title}</p>
                        </div>
                        <div className="w-10 h-10 bg-secondary rounded-full flex items-center justify-center text-secondary-foreground">
                            <User size={20} />
                        </div>
                    </button>

                    {/* Profile Edit Dropdown */}
                    {showProfileEdit && (
                        <div className="absolute right-0 top-full mt-2 w-64 bg-card border border-border rounded-lg shadow-lg z-50 p-4">
                            <h3 className="font-semibold text-sm text-foreground mb-3 flex items-center gap-2">
                                <Edit2 size={14} />
                                Edit Profile
                            </h3>
                            <div className="space-y-3">
                                <div>
                                    <label className="text-xs text-muted-foreground block mb-1">Name</label>
                                    <input
                                        type="text"
                                        value={editName}
                                        onChange={(e) => setEditName(e.target.value)}
                                        className="w-full px-2 py-1.5 text-sm border border-border rounded bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                                        placeholder="Your name"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs text-muted-foreground block mb-1">Job Title</label>
                                    <input
                                        type="text"
                                        value={editTitle}
                                        onChange={(e) => setEditTitle(e.target.value)}
                                        className="w-full px-2 py-1.5 text-sm border border-border rounded bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                                        placeholder="Your title"
                                    />
                                </div>
                                <div className="flex gap-2 pt-2">
                                    <button
                                        onClick={handleSaveProfile}
                                        className="flex-1 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 flex items-center justify-center gap-1"
                                    >
                                        <Check size={12} />
                                        Save
                                    </button>
                                    <button
                                        onClick={() => setShowProfileEdit(false)}
                                        className="px-3 py-1.5 text-xs font-medium border border-border rounded hover:bg-accent"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </header>
    );
}

export default Header;
