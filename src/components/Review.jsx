import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { Check, X, AlertTriangle, Edit2, Save, CheckCircle, Download, Info, Eye, EyeOff, FileText, Loader2, Shield, Wand2, DollarSign, Calculator, Trash2, Columns, Hash, Settings2, ChevronUp, ChevronDown, ArrowUpDown, HelpCircle } from 'lucide-react';
import { cn } from '../lib/utils';

// Import API types for consistent contract
import { TRANSACTION_TYPES, isDisposal, isTransfer, isActionable } from '../lib/api.types';

// Import centralized API client
import { apiGet, apiPost, apiDelete, apiDownload } from '../lib/api.client';

function Review({ assets = [] }) {
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const [localAssets, setLocalAssets] = useState(assets);
    const [filter, setFilter] = useState('all'); // all, errors, review, approved
    const [showExistingAssets, setShowExistingAssets] = useState(false); // Hide existing by default
    const [approvedIds, setApprovedIds] = useState(new Set());
    const [warnings, setWarnings] = useState({ critical: [], warnings: [], info: [], summary: {} });
    const [taxYear, setTaxYear] = useState(new Date().getFullYear());
    const [fyStartMonth, setFyStartMonth] = useState(1); // 1=Jan/Calendar, 4=Apr, 7=Jul, 10=Oct
    const [taxYearLoading, setTaxYearLoading] = useState(false); // Loading state for tax year change
    const [tableCompact, setTableCompact] = useState(false); // Table density: false = comfortable, true = compact
    const [showTechnicalCols, setShowTechnicalCols] = useState(true); // Asset ID, FA CS # - shown by default
    const [showMacrsCols, setShowMacrsCols] = useState(true); // Class, Life, Method, Election
    const [exportStatus, setExportStatus] = useState({ ready: false, reason: null }); // Track export readiness
    const [compatibilityCheck, setCompatibilityCheck] = useState(null); // FA CS compatibility check results
    const [showCompatDialog, setShowCompatDialog] = useState(false); // Show compatibility dialog
    const [depreciationPreview, setDepreciationPreview] = useState(null); // 179/Bonus preview
    const [checkingCompatibility, setCheckingCompatibility] = useState(false);
    const [warningFilter, setWarningFilter] = useState(null); // Filter by warning type: 'misclassified', null
    const [sortConfig, setSortConfig] = useState({ column: null, direction: 'asc' }); // Column sorting

    // FA CS # editing: Track pending values and debounce timers
    const [pendingFacsNumbers, setPendingFacsNumbers] = useState({}); // { uniqueId: pendingValue }
    const facsDebounceTimers = useRef({}); // { uniqueId: timerId }

    // Inline editing: Track pending values for Description, Cost, Date, Transaction Type
    const [pendingDescriptions, setPendingDescriptions] = useState({}); // { uniqueId: pendingValue }
    const [pendingCosts, setPendingCosts] = useState({}); // { uniqueId: pendingValue }
    const [pendingDates, setPendingDates] = useState({}); // { uniqueId: pendingValue }
    const descriptionDebounceTimers = useRef({}); // { uniqueId: timerId }
    const costDebounceTimers = useRef({}); // { uniqueId: timerId }
    const dateDebounceTimers = useRef({}); // { uniqueId: timerId }

    // MACRS Class options for dropdown (matches backend VALID_MACRS_CATEGORIES)
    const MACRS_CLASS_OPTIONS = [
        { value: "Computer Equipment", life: 5, label: "Computer Equipment (5-yr)" },
        { value: "Office Equipment", life: 5, label: "Office Equipment (5-yr)" },
        { value: "Office Furniture", life: 7, label: "Office Furniture (7-yr)" },
        { value: "Machinery & Equipment", life: 7, label: "Machinery & Equipment (7-yr)" },
        { value: "Passenger Automobile", life: 5, label: "Passenger Automobile (5-yr)" },
        { value: "Trucks & Trailers", life: 5, label: "Trucks & Trailers (5-yr)" },
        { value: "Software", life: 3, label: "Software (3-yr)" },
        { value: "Land Improvement", life: 15, label: "Land Improvement (15-yr)" },
        { value: "QIP - Qualified Improvement Property", life: 15, label: "QIP - Qualified Improvement (15-yr)" },
        { value: "Building Equipment", life: 15, label: "Building Equipment (15-yr)" },
        { value: "Residential Rental Property", life: 27.5, label: "Residential Rental (27.5-yr)" },
        { value: "Nonresidential Real Property", life: 39, label: "Commercial Building (39-yr)" },
        { value: "Nondepreciable Land", life: 0, label: "Land (non-depreciable)" },
    ]

    // Fetch warnings and export status when assets change
    useEffect(() => {
        if (assets.length > 0) {
            fetchWarnings();
            fetchTaxConfig();
            fetchExportStatus();
        }
    }, [assets]);

    // Fetch export status whenever approvals change
    // NOTE: Only fetch status, don't sync approvedIds here to avoid infinite loop
    useEffect(() => {
        if (localAssets.length > 0) {
            fetchExportStatusOnly();
        }
    }, [approvedIds]);

    const fetchWarnings = async () => {
        try {
            const data = await apiGet('/warnings');
            setWarnings(data);
        } catch (error) {
            console.error('Failed to fetch warnings:', error);
        }
    };

    const fetchTaxConfig = async () => {
        try {
            const data = await apiGet('/config/tax');
            setTaxYear(data.tax_year);
            setFyStartMonth(data.fy_start_month || 1);
        } catch (error) {
            console.error('Failed to fetch tax config:', error);
        }
    };

    // Fetch export status only (without syncing approvedIds) - used by approvedIds useEffect
    const fetchExportStatusOnly = async () => {
        try {
            const data = await apiGet('/export/status');
            setExportStatus(data);
            // Don't sync approvedIds here - it would cause infinite loop
        } catch (error) {
            console.error('Failed to fetch export status:', error);
        }
    };

    // Fetch export status AND sync approvedIds from backend - used on initial load
    const fetchExportStatus = async () => {
        try {
            const data = await apiGet('/export/status');
            setExportStatus(data);
            // Sync approved IDs from backend on initial load
            if (data.approved_ids) {
                setApprovedIds(new Set(data.approved_ids));
            }
        } catch (error) {
            console.error('Failed to fetch export status:', error);
        }
    };

    // Check FA CS compatibility before export
    const checkFACSCompatibility = async () => {
        setCheckingCompatibility(true);
        try {
            const data = await apiGet('/export/compatibility-check');
            setCompatibilityCheck(data);
            setShowCompatDialog(true);

            // Also fetch depreciation preview
            const preview = await apiGet('/export/depreciation-preview');
            setDepreciationPreview(preview);
        } catch (error) {
            console.error('Failed to check compatibility:', error);
            // Show dialog anyway with error state
            setCompatibilityCheck({ error: error.message });
            setShowCompatDialog(true);
        } finally {
            setCheckingCompatibility(false);
        }
    };

    // Auto-fix compatibility issues
    const autoFixCompatibilityIssues = async () => {
        try {
            const result = await apiPost('/export/auto-fix');
            // Re-check compatibility after fix
            await checkFACSCompatibility();
            // Refresh assets
            const assetsData = await apiGet('/assets');
            if (assetsData && Array.isArray(assetsData)) {
                setLocalAssets(assetsData);
            }
        } catch (error) {
            console.error('Failed to auto-fix:', error);
        }
    };

    const handleTaxYearChange = async (e) => {
        const newYear = parseInt(e.target.value, 10);
        setTaxYearLoading(true);
        try {
            // CRITICAL: Preserve fiscal year start month when changing tax year!
            const data = await apiPost('/config/tax', {
                tax_year: newYear,
                fy_start_month: fyStartMonth  // Preserve current fiscal year setting
            });
            setTaxYear(newYear);

            // Update local assets with reclassified data from the backend
            if (data.assets && Array.isArray(data.assets)) {
                if (data.assets.length > 0) {
                    // Backend returned reclassified assets - use them
                    setLocalAssets(data.assets);
                    setApprovedIds(new Set()); // Clear approvals on reclassification
                } else {
                    // Backend returned empty array - fetch fresh assets
                    console.warn('Tax year change returned no assets, fetching from server...');
                    const assetsData = await apiGet('/assets');
                    if (assetsData && assetsData.length > 0) {
                        setLocalAssets(assetsData);
                        setApprovedIds(new Set());
                    }
                }
            }
            // Refresh warnings and export status for new tax year
            fetchWarnings();
            fetchExportStatus();
        } catch (error) {
            console.error('Failed to update tax year:', error);
        } finally {
            setTaxYearLoading(false);
        }
    };

    // Sync local assets when props change
    useEffect(() => {
        setLocalAssets(assets);
        setApprovedIds(new Set());
    }, [assets]);

    // Calculate stats
    const stats = useMemo(() => {
        const errors = localAssets.filter(a => a.validation_errors?.length > 0).length;
        // ONLY count actionable assets (additions, disposals, transfers) for "Needs Review"
        // Existing assets are excluded - they're already classified in FA CS
        const needsReview = localAssets.filter(a =>
            !a.validation_errors?.length &&
            a.confidence_score <= 0.8 &&
            isActionable(a.transaction_type)
        ).length;
        const highConfidence = localAssets.filter(a =>
            !a.validation_errors?.length && a.confidence_score > 0.8
        ).length;
        const approved = approvedIds.size;
        const totalCost = localAssets.reduce((sum, a) => sum + (a.cost || 0), 0);

        // Count by transaction type
        const allAdditions = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.ADDITION
        );
        const additions = allAdditions.length;

        // De Minimis items (expensed, not capitalized)
        const deMinimisItems = allAdditions.filter(a =>
            a.depreciation_election === 'DeMinimis'
        );
        const deMinimisCount = deMinimisItems.length;
        const deMinimisTotal = deMinimisItems.reduce((sum, a) => sum + (a.cost || 0), 0);
        const capitalAdditions = additions - deMinimisCount;

        // Disposals - all types (for display count)
        const disposals = localAssets.filter(a => isDisposal(a.transaction_type)).length;
        // Current year disposals (actionable)
        const currentYearDisposals = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.CURRENT_YEAR_DISPOSAL ||
            a.transaction_type === TRANSACTION_TYPES.DISPOSAL  // No date - needs review
        ).length;
        // Prior year disposals (not actionable - already processed)
        const priorYearDisposals = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.PRIOR_YEAR_DISPOSAL
        ).length;

        // Transfers - all types (for display count)
        const transfers = localAssets.filter(a => isTransfer(a.transaction_type)).length;
        // Current year transfers (actionable)
        const currentYearTransfers = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.CURRENT_YEAR_TRANSFER ||
            a.transaction_type === TRANSACTION_TYPES.TRANSFER  // No date - needs review
        ).length;
        // Prior year transfers (not actionable - already processed)
        const priorYearTransfers = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.PRIOR_YEAR_TRANSFER
        ).length;

        const existing = localAssets.filter(a =>
            a.transaction_type === TRANSACTION_TYPES.EXISTING
        ).length;
        // Actionable = current year items only (additions + current year disposals/transfers)
        const actionable = additions + currentYearDisposals + currentYearTransfers;

        // Manual entry required - description too vague to classify
        const manualEntry = localAssets.filter(a =>
            a.requires_manual_entry && isActionable(a.transaction_type)
        ).length;

        return {
            total: localAssets.length,
            errors,
            needsReview,
            highConfidence,
            approved,
            totalCost,
            additions,
            capitalAdditions,
            deMinimisCount,
            deMinimisTotal,
            disposals,
            currentYearDisposals,
            priorYearDisposals,
            transfers,
            currentYearTransfers,
            priorYearTransfers,
            existing,
            actionable,
            manualEntry
        };
    }, [localAssets, approvedIds]);

    // Get affected IDs from warnings for filtering/highlighting
    const misclassifiedIds = useMemo(() => {
        // Check both warning types: additions wrongly marked as existing, and existing wrongly marked as additions
        const misclassifiedAsAdditions = warnings.critical?.find(w => w.type === 'MISCLASSIFIED_EXISTING_ASSETS');
        const misclassifiedAsExisting = warnings.critical?.find(w => w.type === 'MISCLASSIFIED_ADDITIONS');
        const ids = new Set([
            ...(misclassifiedAsAdditions?.affected_ids || []),
            ...(misclassifiedAsExisting?.affected_ids || [])
        ]);
        return ids;
    }, [warnings]);

    // Sort handler for column headers
    const handleSort = (column) => {
        setSortConfig(prev => ({
            column,
            direction: prev.column === column && prev.direction === 'asc' ? 'desc' : 'asc'
        }));
    };

    // Sort comparator function
    const sortAssets = (assets, { column, direction }) => {
        if (!column) return assets;

        const sorted = [...assets].sort((a, b) => {
            let aVal, bVal;

            switch (column) {
                case 'status':
                    aVal = a.confidence_score || 0;
                    bVal = b.confidence_score || 0;
                    break;
                case 'asset_id':
                    aVal = (a.asset_id || '').toString().toLowerCase();
                    bVal = (b.asset_id || '').toString().toLowerCase();
                    break;
                case 'fa_cs':
                    aVal = a.fa_cs_asset_number || a.unique_id || 0;
                    bVal = b.fa_cs_asset_number || b.unique_id || 0;
                    break;
                case 'description':
                    aVal = (a.description || '').toLowerCase();
                    bVal = (b.description || '').toLowerCase();
                    break;
                case 'cost':
                    aVal = a.cost || 0;
                    bVal = b.cost || 0;
                    break;
                case 'date':
                    // Use appropriate date based on transaction type
                    aVal = a.disposal_date || a.transfer_date || a.in_service_date || a.acquisition_date || '';
                    bVal = b.disposal_date || b.transfer_date || b.in_service_date || b.acquisition_date || '';
                    break;
                case 'trans_type':
                    aVal = (a.transaction_type || '').toLowerCase();
                    bVal = (b.transaction_type || '').toLowerCase();
                    break;
                case 'class':
                    aVal = (a.macrs_class || '').toLowerCase();
                    bVal = (b.macrs_class || '').toLowerCase();
                    break;
                case 'life':
                    aVal = a.macrs_life || 0;
                    bVal = b.macrs_life || 0;
                    break;
                case 'method':
                    aVal = (a.macrs_method || '').toLowerCase();
                    bVal = (b.macrs_method || '').toLowerCase();
                    break;
                case 'election':
                    aVal = (a.depreciation_election || '').toLowerCase();
                    bVal = (b.depreciation_election || '').toLowerCase();
                    break;
                default:
                    return 0;
            }

            // Handle comparison
            if (typeof aVal === 'number' && typeof bVal === 'number') {
                return direction === 'asc' ? aVal - bVal : bVal - aVal;
            }
            if (aVal < bVal) return direction === 'asc' ? -1 : 1;
            if (aVal > bVal) return direction === 'asc' ? 1 : -1;
            return 0;
        });

        return sorted;
    };

    // Filter assets
    const filteredAssets = useMemo(() => {
        // First apply the showExistingAssets filter
        let baseAssets = localAssets;
        if (!showExistingAssets) {
            // Hide existing assets and prior year disposals/transfers
            // Only show actionable items (additions, current year disposals/transfers)
            baseAssets = localAssets.filter(a =>
                a.transaction_type !== TRANSACTION_TYPES.EXISTING &&
                a.transaction_type !== TRANSACTION_TYPES.PRIOR_YEAR_DISPOSAL &&
                a.transaction_type !== TRANSACTION_TYPES.PRIOR_YEAR_TRANSFER
            );
        }

        // Apply warning filter if active (overrides other filters)
        if (warningFilter === 'misclassified' && misclassifiedIds.size > 0) {
            return sortAssets(localAssets.filter(a => misclassifiedIds.has(a.unique_id)), sortConfig);
        }

        // Then apply the status filter
        let result;
        switch (filter) {
            case 'errors':
                result = baseAssets.filter(a => a.validation_errors?.length > 0);
                break;
            case 'review':
                result = baseAssets.filter(a =>
                    !a.validation_errors?.length && a.confidence_score <= 0.8
                );
                break;
            case 'approved':
                // Use unique_id for approval tracking (unique across sheets)
                result = baseAssets.filter(a => approvedIds.has(a.unique_id));
                break;
            default:
                result = baseAssets;
        }

        // Apply sorting
        return sortAssets(result, sortConfig);
    }, [localAssets, filter, approvedIds, showExistingAssets, warningFilter, misclassifiedIds, sortConfig]);

    // Check if export should be disabled
    const hasBlockingErrors = stats.errors > 0;
    // Only check actionable assets (not existing) for review completion
    const allReviewed = stats.needsReview === 0 ||
        localAssets.filter(a =>
            !a.validation_errors?.length &&
            a.confidence_score <= 0.8 &&
            isActionable(a.transaction_type)
        ).every(a => approvedIds.has(a.unique_id));

    // FA CS Wizard dropdown options by recovery period
    // Must match exact text from FA CS Add Asset Wizard for RPA compatibility
    const FA_CS_WIZARD_OPTIONS = {
        0: [
            "Land (non-depreciable)",
        ],
        5: [
            "Computer, monitor, laptop, PDA, other computer related, property used in research",
            "Automobile - passenger (used over 50% for business)",
            "Light truck or van (actual weight under 13,000 lbs)",
            "Appliance - large (refrigerator, stove, washer, dryer, etc.)",
            "Calculator, copier, fax, noncomputer office machine, typewriter",
        ],
        7: [
            "Furniture and fixtures - office",
            "Machinery and equipment - manufacturing",
        ],
        15: [
            "Land improvement (sidewalk, road, bridge, fence, landscaping)",
            "Qualified improvement property (QIP) - 15 year",
            "Intangible asset - Section 197 (15 year amortization)",
        ],
        27.5: [
            "Residential rental property (27.5 year)",
        ],
        39: [
            "Nonresidential real property (39 year)",
        ],
    };

    // Tax year configuration for dynamic limits
    // CURRENT LAW: OBBBA (One Big Beautiful Bill Act) - enacted July 4, 2025
    // - 100% bonus depreciation PERMANENT for property acquired AND placed in service after 1/19/2025
    // - Section 179: $2.5M limit, $4M phaseout threshold (indexed for inflation)
    // Historical years (2024 and earlier) use rates that were in effect at filing time
    const TAX_YEAR_CONFIG = {
        2020: { section179Limit: 1040000, bonusPercent: 100, source: "Historical" },
        2021: { section179Limit: 1050000, bonusPercent: 100, source: "Historical" },
        2022: { section179Limit: 1080000, bonusPercent: 100, source: "Historical" },
        2023: { section179Limit: 1160000, bonusPercent: 80, source: "Historical" },
        2024: { section179Limit: 1220000, bonusPercent: 60, source: "Historical (Form 4562)" },
        2025: { section179Limit: 2500000, bonusPercent: 100, source: "OBBBA" },
        2026: { section179Limit: 2560000, bonusPercent: 100, source: "OBBBA" },
    };

    // Get tax year limits (with fallback for unknown years)
    // OBBBA: 100% bonus permanent for all new acquisitions (after 1/19/2025)
    const getTaxYearConfig = (year) => {
        if (TAX_YEAR_CONFIG[year]) return TAX_YEAR_CONFIG[year];
        // OBBBA: 100% bonus permanent for 2027+ (indexed Section 179 limits)
        if (year >= 2027) return { section179Limit: 2600000, bonusPercent: 100, source: "OBBBA" };
        return { section179Limit: 1000000, bonusPercent: 100, source: "Historical" };
    };

    const currentYearConfig = getTaxYearConfig(taxYear);

    // De Minimis Safe Harbor threshold
    const DE_MINIMIS_THRESHOLD = 2500;

    // Check if property is real property (can't take bonus depreciation)
    const isRealProperty = (macrsLife) => {
        const life = parseFloat(macrsLife);
        return life === 27.5 || life === 39;
    };

    const handleEditClick = (asset) => {
        // Use unique_id for tracking edit state (unique across sheets)
        setEditingId(asset.unique_id);
        setEditForm({
            macrs_class: asset.macrs_class,
            macrs_life: asset.macrs_life,
            macrs_method: asset.macrs_method,
            fa_cs_wizard_category: asset.fa_cs_wizard_category
        });
    };

    const handleSave = async (uniqueId) => {
        try {
            // Include fa_cs_wizard_category in the update
            const updateData = {
                ...editForm,
                fa_cs_wizard_category: editForm.fa_cs_wizard_category
            };
            // Use unique_id for matching assets (unique across sheets)
            const updatedAssets = localAssets.map(a =>
                a.unique_id === uniqueId ? { ...a, ...updateData, confidence_score: 1.0 } : a
            );
            setLocalAssets(updatedAssets);
            setEditingId(null);

            // Update backend first
            await apiPost(`/assets/${uniqueId}/update`, updateData);

            // Then approve the asset (editing = implicit review/approval)
            await apiPost(`/assets/${uniqueId}/approve`);
            setApprovedIds(prev => new Set([...prev, uniqueId]));
        } catch (error) {
            console.error("Failed to save update:", error);
        }
    };

    const handleElectionChange = async (uniqueId, newElection) => {
        try {
            // Update local state immediately for responsive UI
            setLocalAssets(prev => prev.map(a =>
                a.unique_id === uniqueId
                    ? { ...a, depreciation_election: newElection }
                    : a
            ));
            // Call backend to persist the election change
            await apiPost(`/assets/${uniqueId}/election`, { election: newElection });

            // Refresh depreciation preview to reflect the new election
            // This ensures the preview shows accurate 179/Bonus/MACRS totals
            try {
                const preview = await apiGet('/export/depreciation-preview');
                setDepreciationPreview(preview);
            } catch (previewError) {
                console.warn("Failed to refresh depreciation preview:", previewError);
                // Don't fail the whole operation if preview refresh fails
            }
        } catch (error) {
            console.error("Failed to update election:", error);
        }
    };

    // Generic asset field update (for FA CS #, etc.)
    const handleAssetUpdate = async (uniqueId, updateData) => {
        try {
            // Update local state immediately for responsive UI
            setLocalAssets(prev => prev.map(a =>
                a.unique_id === uniqueId
                    ? { ...a, ...updateData }
                    : a
            ));
            // Call backend to persist the update
            await apiPost(`/assets/${uniqueId}/update`, updateData);
        } catch (error) {
            console.error("Failed to update asset:", error);
        }
    };

    // Debounced FA CS # update handler (500ms delay to prevent API flood)
    const handleFacsNumberChange = useCallback((uniqueId, inputValue) => {
        // Parse the input value
        const parsedValue = inputValue === "" ? null : parseInt(inputValue, 10);

        // Validate: must be null (empty) or positive integer >= 1
        const isValid = parsedValue === null || (Number.isInteger(parsedValue) && parsedValue >= 1);

        if (!isValid) {
            // Invalid input (NaN, 0, negative) - don't update
            return;
        }

        // Store pending value for immediate UI feedback
        setPendingFacsNumbers(prev => ({
            ...prev,
            [uniqueId]: parsedValue
        }));

        // Clear any existing debounce timer for this asset
        if (facsDebounceTimers.current[uniqueId]) {
            clearTimeout(facsDebounceTimers.current[uniqueId]);
        }

        // Set new debounce timer (500ms)
        facsDebounceTimers.current[uniqueId] = setTimeout(async () => {
            try {
                // Update local assets state
                setLocalAssets(prev => prev.map(a =>
                    a.unique_id === uniqueId
                        ? { ...a, fa_cs_asset_number: parsedValue }
                        : a
                ));
                // Clear pending state
                setPendingFacsNumbers(prev => {
                    const updated = { ...prev };
                    delete updated[uniqueId];
                    return updated;
                });
                // Call backend to persist
                await apiPost(`/assets/${uniqueId}/update`, { fa_cs_asset_number: parsedValue });
            } catch (error) {
                console.error("Failed to update FA CS #:", error);
            }
        }, 500);
    }, []);

    // Debounced Description update handler (500ms delay)
    const handleDescriptionChange = useCallback((uniqueId, inputValue) => {
        // Store pending value for immediate UI feedback
        setPendingDescriptions(prev => ({ ...prev, [uniqueId]: inputValue }));

        // Clear any existing debounce timer
        if (descriptionDebounceTimers.current[uniqueId]) {
            clearTimeout(descriptionDebounceTimers.current[uniqueId]);
        }

        // Set new debounce timer
        descriptionDebounceTimers.current[uniqueId] = setTimeout(async () => {
            try {
                setLocalAssets(prev => prev.map(a =>
                    a.unique_id === uniqueId ? { ...a, description: inputValue } : a
                ));
                setPendingDescriptions(prev => {
                    const updated = { ...prev };
                    delete updated[uniqueId];
                    return updated;
                });
                await apiPost(`/assets/${uniqueId}/update`, { description: inputValue });
            } catch (error) {
                console.error("Failed to update description:", error);
            }
        }, 500);
    }, []);

    // Debounced Cost update handler (500ms delay)
    const handleCostChange = useCallback((uniqueId, inputValue) => {
        const parsedValue = inputValue === "" ? 0 : parseFloat(inputValue);
        if (isNaN(parsedValue) || parsedValue < 0) return;

        setPendingCosts(prev => ({ ...prev, [uniqueId]: parsedValue }));

        if (costDebounceTimers.current[uniqueId]) {
            clearTimeout(costDebounceTimers.current[uniqueId]);
        }

        costDebounceTimers.current[uniqueId] = setTimeout(async () => {
            try {
                setLocalAssets(prev => prev.map(a =>
                    a.unique_id === uniqueId ? { ...a, cost: parsedValue } : a
                ));
                setPendingCosts(prev => {
                    const updated = { ...prev };
                    delete updated[uniqueId];
                    return updated;
                });
                await apiPost(`/assets/${uniqueId}/update`, { cost: parsedValue });
            } catch (error) {
                console.error("Failed to update cost:", error);
            }
        }, 500);
    }, []);

    // Debounced Date update handler (500ms delay)
    const handleDateChange = useCallback((uniqueId, inputValue, dateField = 'in_service_date') => {
        setPendingDates(prev => ({ ...prev, [uniqueId]: inputValue }));

        if (dateDebounceTimers.current[uniqueId]) {
            clearTimeout(dateDebounceTimers.current[uniqueId]);
        }

        dateDebounceTimers.current[uniqueId] = setTimeout(async () => {
            try {
                setLocalAssets(prev => prev.map(a =>
                    a.unique_id === uniqueId ? { ...a, [dateField]: inputValue } : a
                ));
                setPendingDates(prev => {
                    const updated = { ...prev };
                    delete updated[uniqueId];
                    return updated;
                });
                await apiPost(`/assets/${uniqueId}/update`, { [dateField]: inputValue });
            } catch (error) {
                console.error("Failed to update date:", error);
            }
        }, 500);
    }, []);

    // Immediate Transaction Type update handler (no debounce - dropdown selection)
    const handleTransactionTypeChange = async (uniqueId, newType) => {
        try {
            setLocalAssets(prev => prev.map(a =>
                a.unique_id === uniqueId ? { ...a, transaction_type: newType } : a
            ));
            await apiPost(`/assets/${uniqueId}/update`, { transaction_type: newType });
        } catch (error) {
            console.error("Failed to update transaction type:", error);
        }
    };

    // Immediate MACRS Class update handler with auto-life population
    const handleMacrsClassChange = async (uniqueId, newClass) => {
        try {
            // Find the corresponding life for this class
            const classOption = MACRS_CLASS_OPTIONS.find(opt => opt.value === newClass);
            const newLife = classOption ? classOption.life : 7; // Default to 7 if not found

            setLocalAssets(prev => prev.map(a =>
                a.unique_id === uniqueId
                    ? { ...a, macrs_class: newClass, macrs_life: newLife, confidence_score: 1.0 }
                    : a
            ));
            await apiPost(`/assets/${uniqueId}/update`, {
                macrs_class: newClass,
                macrs_life: newLife
            });
        } catch (error) {
            console.error("Failed to update MACRS class:", error);
        }
    };

    const handleApprove = async (uniqueId) => {
        try {
            // Call backend to record approval
            await apiPost(`/assets/${uniqueId}/approve`);
            setApprovedIds(prev => new Set([...prev, uniqueId]));
        } catch (error) {
            console.error("Failed to approve asset:", error);
            alert(`Failed to approve: ${error.message || 'Unknown error'}`);
        }
    };

    const handleUnapprove = async (uniqueId) => {
        try {
            // Call backend to remove approval (DELETE request)
            await apiDelete(`/assets/${uniqueId}/approve`);
            setApprovedIds(prev => {
                const newSet = new Set(prev);
                newSet.delete(uniqueId);
                return newSet;
            });
        } catch (error) {
            console.error("Failed to unapprove asset:", error);
            alert(`Failed to unapprove: ${error.message || 'Unknown error'}`);
        }
    };

    // Remove asset from session (for incorrectly imported rows)
    const handleRemove = async (uniqueId, assetDescription) => {
        // Confirm before deletion
        const confirmed = window.confirm(
            `Remove "${assetDescription || 'this asset'}" from the import?\n\n` +
            `This will remove it from the current session. It won't affect the original Excel file.`
        );
        if (!confirmed) return;

        try {
            await apiDelete(`/assets/${uniqueId}`);
            // Remove from local state
            setLocalAssets(prev => prev.filter(a => a.unique_id !== uniqueId));
            // Also remove from approved set if it was approved
            setApprovedIds(prev => {
                const newSet = new Set(prev);
                newSet.delete(uniqueId);
                return newSet;
            });
            // Refresh warnings and export status
            fetchWarnings();
            fetchExportStatusOnly();
        } catch (error) {
            console.error("Failed to remove asset:", error);
            alert(`Failed to remove: ${error.message || 'Unknown error'}`);
        }
    };

    const handleApproveAllHighConfidence = async () => {
        try {
            // Get all high confidence asset IDs
            const highConfIds = localAssets
                .filter(a => !a.validation_errors?.length && a.confidence_score > 0.8)
                .map(a => a.unique_id);

            if (highConfIds.length === 0) return;

            // Batch approve on backend
            await apiPost('/assets/approve-batch', highConfIds);
            setApprovedIds(prev => new Set([...prev, ...highConfIds]));
        } catch (error) {
            console.error("Failed to approve batch:", error);
            alert(`Failed to approve: ${error.message || 'Unknown error'}`);
        }
    };

    // Approve all currently visible (filtered) assets
    const handleApproveAllVisible = async () => {
        try {
            // Get IDs of visible assets that can be approved (no errors, not already approved)
            const visibleApprovableIds = filteredAssets
                .filter(a => !a.validation_errors?.length && !approvedIds.has(a.unique_id))
                .map(a => a.unique_id);

            if (visibleApprovableIds.length === 0) return;

            // Batch approve on backend
            await apiPost('/assets/approve-batch', visibleApprovableIds);
            setApprovedIds(prev => new Set([...prev, ...visibleApprovableIds]));
        } catch (error) {
            console.error("Failed to approve batch:", error);
            alert(`Failed to approve: ${error.message || 'Unknown error'}`);
        }
    };

    // Helper function to download file without opening new window (works in Electron)
    const downloadFile = async (endpoint, defaultFilename) => {
        try {
            const blob = await apiDownload(endpoint);

            // Trigger browser download
            const blobUrl = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = defaultFilename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
        } catch (error) {
            alert(`Export blocked: ${error.message || 'Unknown error'}`);
        }
    };

    const handleExport = () => {
        // Double-check export readiness before attempting
        if (!exportStatus.ready) {
            alert(`Cannot export: ${exportStatus.reason || 'Not all assets are approved'}`);
            return;
        }
        downloadFile('/export', 'FA_CS_Import.xlsx');
    };

    const handleAuditReport = () => {
        downloadFile('/export/audit', 'Audit_Report.xlsx');
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
        <TooltipProvider delayDuration={200}>
        <div className="p-6 max-w-[1900px] mx-auto">
            {/* Header */}
            <div className="flex justify-between items-start mb-6">
                <div>
                    <div className="flex items-center gap-3">
                        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                            Review & Approve
                        </h1>
                        <div className="relative inline-block">
                            <select
                                value={taxYear}
                                onChange={handleTaxYearChange}
                                disabled={taxYearLoading}
                                className={cn(
                                    "px-3 py-1 text-sm font-semibold bg-blue-100 text-blue-800 rounded-full border border-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-400 appearance-none pr-8",
                                    taxYearLoading ? "opacity-50 cursor-wait" : "cursor-pointer hover:bg-blue-200"
                                )}
                            >
                                {[2020, 2021, 2022, 2023, 2024, 2025, 2026].map(year => (
                                    <option key={year} value={year}>Tax Year {year}</option>
                                ))}
                            </select>
                            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2 text-blue-800">
                                {taxYearLoading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                    </svg>
                                )}
                            </div>
                        </div>
                        {/* Fiscal Year Indicator Badge */}
                        {fyStartMonth !== 1 && (
                            <span className="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-800 rounded-full border border-amber-200">
                                {fyStartMonth === 4 ? 'Apr-Mar' : fyStartMonth === 7 ? 'Jul-Jun' : fyStartMonth === 10 ? 'Oct-Sep' : `Month ${fyStartMonth}`} FY
                            </span>
                        )}
                        {fyStartMonth === 1 && (
                            <span className="px-2 py-1 text-xs font-medium bg-slate-100 text-slate-600 rounded-full border border-slate-200">
                                Calendar Year
                            </span>
                        )}
                    </div>
                    <p className="text-slate-500 dark:text-slate-400 mt-2">
                        Review AI classifications before export. Low confidence items need your attention.
                    </p>
                </div>
                <div className="flex gap-3">
                    <Button
                        variant="outline"
                        onClick={handleApproveAllHighConfidence}
                        className="text-green-600 hover:bg-green-50"
                    >
                        <CheckCircle className="w-4 h-4 mr-2" />
                        Approve All High Confidence
                    </Button>
                    <Button
                        variant="outline"
                        onClick={handleApproveAllVisible}
                        disabled={filteredAssets.filter(a => !a.validation_errors?.length && !approvedIds.has(a.unique_id)).length === 0}
                        className={cn(
                            filteredAssets.filter(a => !a.validation_errors?.length && !approvedIds.has(a.unique_id)).length === 0
                                ? "text-gray-400 cursor-not-allowed"
                                : "text-blue-600 hover:bg-blue-50"
                        )}
                        title={`Approve all ${filteredAssets.filter(a => !a.validation_errors?.length && !approvedIds.has(a.unique_id)).length} visible unapproved assets`}
                    >
                        <Check className="w-4 h-4 mr-2" />
                        Approve Visible ({filteredAssets.filter(a => !a.validation_errors?.length && !approvedIds.has(a.unique_id)).length})
                    </Button>
                    <Button
                        variant="outline"
                        onClick={handleAuditReport}
                        disabled={!exportStatus.ready}
                        className={cn(
                            !exportStatus.ready
                                ? "text-gray-400 cursor-not-allowed"
                                : "text-slate-600 hover:bg-slate-50"
                        )}
                        title={exportStatus.ready
                            ? "Download full asset schedule for IRS audit documentation"
                            : `Cannot export audit report: ${exportStatus.reason || 'Not all actionable items approved'}`}
                    >
                        <FileText className="w-4 h-4 mr-2" />
                        Audit Documentation
                    </Button>
                    <Button
                        onClick={checkFACSCompatibility}
                        disabled={!exportStatus.ready || checkingCompatibility}
                        title={exportStatus.ready ? "Check FA CS compatibility and export" : exportStatus.reason || "Not ready to export"}
                        className={cn(
                            "text-white",
                            !exportStatus.ready
                                ? "bg-gray-400 cursor-not-allowed"
                                : "bg-green-600 hover:bg-green-700"
                        )}
                    >
                        {checkingCompatibility ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <Shield className="w-4 h-4 mr-2" />
                        )}
                        FA CS Prep Workpaper
                    </Button>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-5 gap-4 mb-6">
                <div
                    onClick={() => setFilter('all')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'all' ? "border-blue-500 bg-blue-50" : "border-slate-200 hover:border-slate-300"
                    )}
                >
                    <div className="text-2xl font-bold text-slate-900">{stats.total}</div>
                    <div className="text-sm text-slate-500">Total Assets</div>
                    <div className="text-xs text-slate-400 mt-1">${stats.totalCost.toLocaleString()}</div>
                </div>
                <div
                    onClick={() => setFilter('errors')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'errors' ? "border-red-500 bg-red-50" : "border-slate-200 hover:border-slate-300",
                        stats.errors > 0 && "border-red-200 bg-red-50"
                    )}
                >
                    <div className={cn("text-2xl font-bold", stats.errors > 0 ? "text-red-600" : "text-slate-900")}>
                        {stats.errors}
                    </div>
                    <div className="text-sm text-slate-500">Errors</div>
                    <div className="text-xs text-red-500 mt-1">{stats.errors > 0 ? "Must fix before export" : "None"}</div>
                </div>
                <div
                    onClick={() => setFilter('review')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'review' ? "border-yellow-500 bg-yellow-50" : "border-slate-200 hover:border-slate-300"
                    )}
                >
                    <div className="text-2xl font-bold text-yellow-600">{stats.needsReview}</div>
                    <div className="text-sm text-slate-500">Needs Review</div>
                    <div className="text-xs text-slate-400 mt-1">Low confidence</div>
                </div>
                <div
                    className="p-4 rounded-lg border border-slate-200 cursor-default"
                >
                    <div className="text-2xl font-bold text-green-600">{stats.highConfidence}</div>
                    <div className="text-sm text-slate-500">High Confidence</div>
                    <div className="text-xs text-slate-400 mt-1">&gt;80% confidence</div>
                </div>
                <div
                    onClick={() => setFilter('approved')}
                    className={cn(
                        "p-4 rounded-lg border cursor-pointer transition-all",
                        filter === 'approved' ? "border-green-500 bg-green-50" : "border-slate-200 hover:border-slate-300"
                    )}
                >
                    <div className="text-2xl font-bold text-green-600">{stats.approved}</div>
                    <div className="text-sm text-slate-500">Approved</div>
                    <div className="text-xs text-slate-400 mt-1">Ready to export</div>
                </div>
            </div>

            {/* Critical Warnings Banner */}
            {warnings.critical?.length > 0 && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                    <div className="flex items-center gap-2 text-red-800 font-semibold mb-2">
                        <AlertTriangle className="w-5 h-5" />
                        Critical Compliance Warnings ({warnings.critical.length})
                    </div>
                    {warnings.critical.slice(0, 2).map((warning, idx) => (
                        <div key={idx} className="text-sm text-red-700 mb-1">
                            <strong>{warning.type}:</strong> {warning.message}
                            {warning.affected_ids?.length > 0 ? (
                                <button
                                    onClick={() => {
                                        if (warningFilter === 'misclassified') {
                                            setWarningFilter(null);
                                            setShowExistingAssets(false); // Reset to actionable only
                                        } else {
                                            setWarningFilter('misclassified');
                                            setShowExistingAssets(true); // Show all to see misclassified
                                        }
                                    }}
                                    className={cn(
                                        "ml-2 px-2 py-0.5 rounded text-xs font-medium transition-colors",
                                        warningFilter === 'misclassified'
                                            ? "bg-red-600 text-white hover:bg-red-700"
                                            : "bg-red-200 text-red-800 hover:bg-red-300"
                                    )}
                                >
                                    {warningFilter === 'misclassified' ? '✓ Showing' : 'Show'} {warning.affected_count} assets
                                </button>
                            ) : (
                                <span className="text-red-600 ml-2">({warning.affected_count} assets)</span>
                            )}
                        </div>
                    ))}
                    {warningFilter === 'misclassified' && (
                        <div className="text-xs text-red-800 mt-2 font-medium flex items-center gap-2">
                            <Eye className="w-3 h-3" />
                            Showing only misclassified assets.
                            <button
                                onClick={() => { setWarningFilter(null); setShowExistingAssets(false); }}
                                className="underline hover:no-underline"
                            >
                                Clear filter
                            </button>
                        </div>
                    )}
                    {!warningFilter && (
                        <div className="text-xs text-red-600 mt-2">
                            Go to Settings to configure tax year and resolve warnings.
                        </div>
                    )}
                </div>
            )}

            {/* Error Banner */}
            {hasBlockingErrors && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                    <div>
                        <div className="font-medium text-red-800">
                            {stats.errors} asset(s) have validation errors
                        </div>
                        <div className="text-sm text-red-600">
                            Fix all errors before exporting to Fixed Asset CS
                        </div>
                    </div>
                </div>
            )}

            {/* View Toggle - Actionable vs All Assets */}
            <div className="mb-4 p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-700">View:</span>
                        <button
                            onClick={() => setShowExistingAssets(false)}
                            className={cn(
                                "px-3 py-1.5 rounded-lg text-sm font-medium transition-all",
                                !showExistingAssets
                                    ? "bg-blue-600 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            Actionable Only ({stats.actionable})
                        </button>
                        <button
                            onClick={() => setShowExistingAssets(true)}
                            className={cn(
                                "px-3 py-1.5 rounded-lg text-sm font-medium transition-all",
                                showExistingAssets
                                    ? "bg-blue-600 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            All Assets ({stats.total})
                        </button>
                    </div>
                    <div className="h-6 w-px bg-slate-300" />
                    <div className="flex items-center gap-3 text-xs text-slate-500">
                        <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded">
                            {stats.capitalAdditions} Additions
                        </span>
                        {stats.deMinimisCount > 0 && (
                            <span
                                className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded cursor-help"
                                title={`$${stats.deMinimisTotal.toLocaleString()} expensed via De Minimis Safe Harbor - NOT added to FA CS`}
                            >
                                {stats.deMinimisCount} Expensed
                            </span>
                        )}
                        <span
                            className="bg-red-100 text-red-700 px-2 py-0.5 rounded cursor-help"
                            title={stats.priorYearDisposals > 0
                                ? `${stats.currentYearDisposals} current year (actionable) + ${stats.priorYearDisposals} prior year (already processed)`
                                : `${stats.currentYearDisposals} disposals in current tax year`}
                        >
                            {stats.currentYearDisposals} Disposals
                            {stats.priorYearDisposals > 0 && (
                                <span className="text-red-400 ml-1">(+{stats.priorYearDisposals} prior)</span>
                            )}
                        </span>
                        <span
                            className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded cursor-help"
                            title={stats.priorYearTransfers > 0
                                ? `${stats.currentYearTransfers} current year (actionable) + ${stats.priorYearTransfers} prior year (already processed)`
                                : `${stats.currentYearTransfers} transfers in current tax year`}
                        >
                            {stats.currentYearTransfers} Transfers
                            {stats.priorYearTransfers > 0 && (
                                <span className="text-purple-400 ml-1">(+{stats.priorYearTransfers} prior)</span>
                            )}
                        </span>
                        {showExistingAssets && (
                            <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                                {stats.existing} Existing
                            </span>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    {/* Table Density Toggle */}
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500">Density:</span>
                        <button
                            onClick={() => setTableCompact(false)}
                            className={cn(
                                "px-2 py-1 rounded text-xs font-medium transition-all",
                                !tableCompact
                                    ? "bg-slate-700 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            Comfortable
                        </button>
                        <button
                            onClick={() => setTableCompact(true)}
                            className={cn(
                                "px-2 py-1 rounded text-xs font-medium transition-all",
                                tableCompact
                                    ? "bg-slate-700 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                        >
                            Compact
                        </button>
                    </div>
                    <div className="h-4 w-px bg-slate-300" />
                    {/* Column Visibility Toggles */}
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500">Columns:</span>
                        <button
                            onClick={() => setShowTechnicalCols(!showTechnicalCols)}
                            className={cn(
                                "px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1",
                                showTechnicalCols
                                    ? "bg-blue-600 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                            title="Show/hide Asset ID and FA CS # columns"
                        >
                            <Hash className="w-3 h-3" />
                            IDs
                        </button>
                        <button
                            onClick={() => setShowMacrsCols(!showMacrsCols)}
                            className={cn(
                                "px-2 py-1 rounded text-xs font-medium transition-all flex items-center gap-1",
                                showMacrsCols
                                    ? "bg-blue-600 text-white"
                                    : "bg-white text-slate-600 border border-slate-300 hover:bg-slate-100"
                            )}
                            title="Show/hide MACRS classification details (Class, Life, Method, Election)"
                        >
                            <Settings2 className="w-3 h-3" />
                            MACRS
                        </button>
                    </div>
                    {!showExistingAssets && stats.existing > 0 && (
                        <div className="text-xs text-slate-500 flex items-center gap-1">
                            <EyeOff className="w-3 h-3" />
                            {stats.existing} existing assets hidden (no action required)
                        </div>
                    )}
                </div>
            </div>

            {/* Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="overflow-x-auto">
                        <table className={cn(
                            "w-full text-left",
                            tableCompact ? "text-xs" : "text-sm"
                        )} style={{
                            tableLayout: 'fixed',
                            minWidth: `${700 + (showTechnicalCols ? 140 : 0) + (showMacrsCols ? 335 : 0)}px`
                        }}>
                            <thead className={cn(
                                "text-xs text-slate-500 uppercase bg-slate-50 dark:bg-slate-900/50 border-b",
                                tableCompact ? "text-[10px]" : "text-xs"
                            )}>
                                <tr>
                                    {/* Sortable column header helper */}
                                    {(() => {
                                        const SortIcon = ({ column }) => {
                                            if (sortConfig.column !== column) {
                                                return <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />;
                                            }
                                            return sortConfig.direction === 'asc'
                                                ? <ChevronUp className="w-3 h-3 text-blue-600" />
                                                : <ChevronDown className="w-3 h-3 text-blue-600" />;
                                        };

                                        const SortableHeader = ({ column, children, style, className, title }) => (
                                            <th
                                                className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3", className)}
                                                style={style}
                                                onClick={() => handleSort(column)}
                                                title={title || `Click to sort by ${column}`}
                                            >
                                                <span className="flex items-center gap-1">
                                                    {children}
                                                    <SortIcon column={column} />
                                                </span>
                                            </th>
                                        );

                                        return null;
                                    })()}
                                    <th
                                        className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                        style={{ width: '80px', minWidth: '70px', resize: 'horizontal', overflow: 'hidden' }}
                                        onClick={() => handleSort('status')}
                                        title="Sort by confidence score"
                                    >
                                        <span className="flex items-center gap-1">
                                            Status
                                            {sortConfig.column === 'status'
                                                ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                            }
                                        </span>
                                    </th>
                                    {showTechnicalCols && (
                                        <th
                                            className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                            style={{ width: '70px', minWidth: '55px', resize: 'horizontal', overflow: 'hidden' }}
                                            onClick={() => handleSort('asset_id')}
                                            title="Sort by Asset ID"
                                        >
                                            <span className="flex items-center gap-1">
                                                Asset ID
                                                {sortConfig.column === 'asset_id'
                                                    ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                    : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                                }
                                            </span>
                                        </th>
                                    )}
                                    {showTechnicalCols && (
                                        <th
                                            className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                            style={{ width: '60px', minWidth: '50px', resize: 'horizontal', overflow: 'hidden' }}
                                            onClick={() => handleSort('fa_cs')}
                                            title="Sort by FA CS # - Click to sort"
                                        >
                                            <span className="flex items-center gap-1">
                                                FA CS #
                                                {sortConfig.column === 'fa_cs'
                                                    ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                    : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                                }
                                            </span>
                                        </th>
                                    )}
                                    <th
                                        className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                        style={{ width: showTechnicalCols ? '180px' : '240px', minWidth: '100px', resize: 'horizontal', overflow: 'hidden' }}
                                        onClick={() => handleSort('description')}
                                        title="Sort by Description"
                                    >
                                        <span className="flex items-center gap-1">
                                            Description
                                            {sortConfig.column === 'description'
                                                ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                            }
                                        </span>
                                    </th>
                                    <th
                                        className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                        style={{ width: '175px', minWidth: '120px', resize: 'horizontal', overflow: 'hidden' }}
                                        onClick={() => handleSort('cost')}
                                        title="Sort by Cost"
                                    >
                                        <span className="flex items-center gap-1">
                                            Cost
                                            {sortConfig.column === 'cost'
                                                ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                            }
                                        </span>
                                    </th>
                                    <th
                                        className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                        style={{ width: '95px', minWidth: '85px', resize: 'horizontal', overflow: 'hidden' }}
                                        onClick={() => handleSort('date')}
                                        title="Sort by Key Date (In Service / Disposal / Transfer date)"
                                    >
                                        <span className="flex items-center gap-1">
                                            Key Date
                                            {sortConfig.column === 'date'
                                                ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                            }
                                            <Info className="w-3 h-3 text-slate-400" />
                                        </span>
                                    </th>
                                    <th
                                        className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                        style={{ width: '85px', minWidth: '70px', resize: 'horizontal', overflow: 'hidden' }}
                                        onClick={() => handleSort('trans_type')}
                                        title="Sort by Transaction Type"
                                    >
                                        <span className="flex items-center gap-1">
                                            Trans. Type
                                            {sortConfig.column === 'trans_type'
                                                ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                            }
                                        </span>
                                    </th>
                                    {showMacrsCols && (
                                        <th
                                            className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                            style={{ width: '85px', minWidth: '60px', resize: 'horizontal', overflow: 'hidden' }}
                                            onClick={() => handleSort('class')}
                                            title="Sort by MACRS Class"
                                        >
                                            <span className="flex items-center gap-1">
                                                Class
                                                {sortConfig.column === 'class'
                                                    ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                    : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                                }
                                            </span>
                                        </th>
                                    )}
                                    {showMacrsCols && (
                                        <th
                                            className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                            style={{ width: '50px', minWidth: '40px', resize: 'horizontal', overflow: 'hidden' }}
                                            onClick={() => handleSort('life')}
                                            title="Sort by MACRS Life"
                                        >
                                            <span className="flex items-center gap-1">
                                                Life
                                                {sortConfig.column === 'life'
                                                    ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                    : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                                }
                                            </span>
                                        </th>
                                    )}
                                    {showMacrsCols && (
                                        <th
                                            className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                            style={{ width: '60px', minWidth: '50px', resize: 'horizontal', overflow: 'hidden' }}
                                            onClick={() => handleSort('method')}
                                            title="Sort by Depreciation Method"
                                        >
                                            <span className="flex items-center gap-1">
                                                Method
                                                {sortConfig.column === 'method'
                                                    ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                    : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                                }
                                            </span>
                                        </th>
                                    )}
                                    {showMacrsCols && (
                                        <th
                                            className={cn("resizable-col group cursor-pointer hover:bg-slate-100 transition-colors", tableCompact ? "px-2 py-2" : "px-3 py-3")}
                                            style={{ width: '115px', minWidth: '100px', resize: 'horizontal', overflow: 'hidden' }}
                                            onClick={() => handleSort('election')}
                                            title="Sort by Depreciation Election"
                                        >
                                            <span className="flex items-center gap-1">
                                                Election
                                                <span className="text-[9px] bg-blue-100 text-blue-700 px-1 rounded">179/Bonus</span>
                                                {sortConfig.column === 'election'
                                                    ? (sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3 text-blue-600" /> : <ChevronDown className="w-3 h-3 text-blue-600" />)
                                                    : <ArrowUpDown className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
                                                }
                                            </span>
                                        </th>
                                    )}
                                    <th className={cn(tableCompact ? "px-2 py-2" : "px-3 py-3")} style={{ width: '90px', minWidth: '80px' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredAssets.map((asset) => {
                                    // Use unique_id for approval tracking (unique across sheets)
                                    const isApproved = approvedIds.has(asset.unique_id);
                                    const hasErrors = asset.validation_errors?.length > 0;
                                    const isDeMinimis = asset.depreciation_election === 'DeMinimis';
                                    // Only actionable items need review (not existing assets, not De Minimis)
                                    // De Minimis items don't need classification review - they're expensed
                                    const needsReview = !hasErrors && asset.confidence_score <= 0.8 && isActionable(asset.transaction_type) && !isDeMinimis;
                                    // Hide MACRS fields for De Minimis (expensed), Disposals, and Transfers
                                    const isDisposalOrTransfer = isDisposal(asset.transaction_type) || isTransfer(asset.transaction_type);
                                    const hideMacrsFields = isDeMinimis || isDisposalOrTransfer;
                                    const isMisclassified = misclassifiedIds.has(asset.unique_id);

                                    return (
                                        <tr
                                            key={asset.unique_id}
                                            className={cn(
                                                "border-b hover:bg-slate-50 dark:border-slate-800",
                                                hasErrors && "bg-red-50/50",
                                                asset.requires_manual_entry && !isApproved && "bg-orange-50/40",
                                                needsReview && !isApproved && !asset.requires_manual_entry && "bg-yellow-50/30",
                                                isApproved && "bg-green-50/30",
                                                isDeMinimis && "bg-emerald-50/40 opacity-75",
                                                isMisclassified && "bg-red-100/60 border-l-4 border-l-red-500"
                                            )}
                                        >
                                            {/* Status + Confidence combined */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <div className="flex flex-col items-start gap-0.5">
                                                    {/* Status badge */}
                                                    {hasErrors ? (
                                                        <span
                                                            className={cn(
                                                                "inline-flex items-center rounded-full font-medium bg-red-100 text-red-800 cursor-help",
                                                                tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                            )}
                                                            title={asset.validation_errors?.join('\n• ')}
                                                        >
                                                            <AlertTriangle className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                            Error
                                                        </span>
                                                    ) : isApproved ? (
                                                        <span
                                                            className={cn(
                                                                "inline-flex items-center rounded-full font-medium bg-green-100 text-green-800 cursor-pointer hover:bg-green-200",
                                                                tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                            )}
                                                            onClick={() => handleUnapprove(asset.unique_id)}
                                                            title="Click to unapprove"
                                                        >
                                                            <Check className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                            Approved
                                                        </span>
                                                    ) : isDeMinimis ? (
                                                        // De Minimis - No classification needed, will be expensed
                                                        <span
                                                            className={cn(
                                                                "inline-flex items-center rounded-full font-medium bg-emerald-100 text-emerald-700 cursor-help",
                                                                tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                            )}
                                                            title={`De Minimis Safe Harbor\n✓ Will be expensed immediately\n✓ No FA CS entry needed\n✓ No classification required\n\n📋 Rev. Proc. 2015-20\nItems under the de minimis threshold are expensed rather than capitalized.`}
                                                        >
                                                            <DollarSign className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                            Expense
                                                        </span>
                                                    ) : asset.requires_manual_entry ? (
                                                        // Manual Entry Required - Description doesn't identify the asset
                                                        <span
                                                            className={cn(
                                                                "inline-flex items-center rounded-full font-medium bg-orange-100 text-orange-800 cursor-help",
                                                                tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                            )}
                                                            title={`Manual Entry Required\n\n⚠ Description doesn't identify the asset type:\n${(asset.quality_issues || []).map(i => `  • ${i}`).join('\n') || '  • Vague or incomplete description'}\n\n❌ Cannot reliably classify this asset\n→ User must manually specify the asset class\n→ Or update the description to identify what was purchased\n\n📋 Examples of good descriptions:\n  ✓ "Dell Optiplex 7090 Desktop"\n  ✓ "2023 Ford F-150 Truck"\n  ✓ "Herman Miller Office Chair"\n\n❌ Examples of bad descriptions:\n  ✗ "Amazon" (vendor only)\n  ✗ "Lamprecht" (shipping company)\n  ✗ "Invoice #1234" (not an asset)`}
                                                        >
                                                            <HelpCircle className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                            Manual
                                                        </span>
                                                    ) : asset.confidence_score > 0.8 ? (
                                                        <span
                                                            className={cn(
                                                                "inline-flex items-center rounded-full font-medium bg-green-50 text-green-700 cursor-help",
                                                                tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                            )}
                                                            title={
                                                                asset.transaction_type?.includes('Disposal')
                                                                    ? `Complete Data (${Math.round((asset.confidence_score || 0) * 100)}%)\n✓ Disposal date recorded\n✓ Cost/basis available\n✓ Ready for gain/loss calculation`
                                                                    : asset.transaction_type?.includes('Transfer')
                                                                    ? `Complete Data (${Math.round((asset.confidence_score || 0) * 100)}%)\n✓ Transfer date recorded\n✓ Location info available\n✓ Ready for transfer documentation`
                                                                    : `High Confidence (${Math.round((asset.confidence_score || 0) * 100)}%)\n✓ Description matched known asset patterns\n✓ Recovery period matches asset class\n✓ Cost within expected range`
                                                            }
                                                        >
                                                            High Conf.
                                                        </span>
                                                    ) : (
                                                        <span
                                                            className={cn(
                                                                "inline-flex items-center rounded-full font-medium bg-yellow-100 text-yellow-800 cursor-help",
                                                                tableCompact ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
                                                            )}
                                                            title={(() => {
                                                                // Smart suggestion based on asset data
                                                                const desc = (asset.description || '').toLowerCase();
                                                                let suggestion = '';

                                                                // Suggest based on description keywords
                                                                if (desc.includes('computer') || desc.includes('laptop') || desc.includes('server')) {
                                                                    suggestion = '\n\n💡 Suggestion: Likely 5-year Computer Equipment';
                                                                } else if (desc.includes('furniture') || desc.includes('desk') || desc.includes('chair')) {
                                                                    suggestion = '\n\n💡 Suggestion: Likely 7-year Furniture & Fixtures';
                                                                } else if (desc.includes('vehicle') || desc.includes('truck') || desc.includes('car')) {
                                                                    suggestion = '\n\n💡 Suggestion: Likely 5-year Vehicles';
                                                                } else if (desc.includes('building') || desc.includes('hvac') || desc.includes('roof')) {
                                                                    suggestion = '\n\n💡 Suggestion: Likely 39-year Real Property';
                                                                } else if (desc.includes('software') || desc.includes('license')) {
                                                                    suggestion = '\n\n💡 Suggestion: Likely 3-year Software';
                                                                } else if (desc.includes('equipment') || desc.includes('machine')) {
                                                                    suggestion = '\n\n💡 Suggestion: Likely 7-year Equipment';
                                                                }

                                                                // Include classification_reason if available
                                                                const reason = asset.classification_reason ? `\n📋 ${asset.classification_reason}` : '';

                                                                return asset.transaction_type?.includes('Disposal')
                                                                    ? `Incomplete Data (${Math.round((asset.confidence_score || 0) * 100)}%)\n⚠ Missing disposal date or cost\n⚠ Cannot calculate gain/loss\n→ Add missing data for processing${reason}`
                                                                    : asset.transaction_type?.includes('Transfer')
                                                                    ? `Incomplete Data (${Math.round((asset.confidence_score || 0) * 100)}%)\n⚠ Missing transfer date or locations\n⚠ Incomplete transfer record\n→ Add from/to location info${reason}`
                                                                    : asset.confidence_score > 0.5
                                                                    ? `Medium Confidence (${Math.round((asset.confidence_score || 0) * 100)}%)\n⚠ Partial description match\n⚠ Multiple possible classifications\n→ Recommend manual review${reason}${suggestion}`
                                                                    : `Low Confidence (${Math.round((asset.confidence_score || 0) * 100)}%)\n✗ Unknown or ambiguous asset type\n✗ Insufficient data for classification\n→ Manual classification required${reason}${suggestion}`;
                                                            })()}
                                                        >
                                                            <AlertTriangle className={tableCompact ? "w-2.5 h-2.5 mr-0.5" : "w-3 h-3 mr-1"} />
                                                            Review
                                                            {/* Show wand icon if we have a smart suggestion */}
                                                            {!asset.transaction_type?.includes('Disposal') && !asset.transaction_type?.includes('Transfer') && (
                                                                ((asset.description || '').toLowerCase().match(/computer|laptop|server|furniture|desk|chair|vehicle|truck|car|building|hvac|roof|software|license|equipment|machine/)) && (
                                                                    <Wand2 className={cn(
                                                                        "ml-0.5 text-purple-600",
                                                                        tableCompact ? "w-2.5 h-2.5" : "w-3 h-3"
                                                                    )} />
                                                                )
                                                            )}
                                                        </span>
                                                    )}
                                                    {/* Confidence % below the badge - N/A for De Minimis */}
                                                    <span
                                                        className={cn(
                                                            "font-mono",
                                                            tableCompact ? "text-[9px]" : "text-[10px]",
                                                            isDeMinimis ? "text-slate-400" :
                                                                asset.confidence_score > 0.8 ? "text-green-600" :
                                                                    asset.confidence_score > 0.5 ? "text-yellow-600" : "text-red-600"
                                                        )}
                                                    >
                                                        {isDeMinimis ? "N/A" : `${Math.round((asset.confidence_score || 0) * 100)}%`}
                                                    </span>
                                                </div>
                                            </td>
                                            {/* Asset ID (Client's ID) - Collapsible */}
                                            {showTechnicalCols && (
                                                <td className={cn(
                                                    "font-medium text-slate-900 dark:text-white",
                                                    tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                                )}>
                                                    {asset.asset_id || "-"}
                                                </td>
                                            )}
                                            {/* FA CS # (Editable - maps to FA CS numeric Asset #) - Collapsible */}
                                            {showTechnicalCols && (
                                                <td className={cn(
                                                    "text-slate-600",
                                                    tableCompact ? "px-1 py-1" : "px-2 py-1.5"
                                                )}>
                                                    <input
                                                        type="number"
                                                        min="1"
                                                        className={cn(
                                                            "w-full border rounded text-center font-mono",
                                                            tableCompact ? "px-1 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
                                                            // Show pending state while debouncing
                                                            pendingFacsNumbers[asset.unique_id] !== undefined
                                                                ? "border-yellow-300 bg-yellow-50"
                                                                : asset.fa_cs_asset_number
                                                                    ? "border-blue-300 bg-blue-50"
                                                                    : "border-slate-200 bg-white",
                                                            "focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                        )}
                                                        placeholder={(() => {
                                                            // Calculate auto-generated FA CS # (same logic as backend)
                                                            if (asset.asset_id) {
                                                                const match = String(asset.asset_id).match(/(\d+)/);
                                                                return match ? match[1] : String(asset.row_index);
                                                            }
                                                            return String(asset.row_index);
                                                        })()}
                                                        value={
                                                            // Show pending value if debouncing, else actual value
                                                            pendingFacsNumbers[asset.unique_id] !== undefined
                                                                ? (pendingFacsNumbers[asset.unique_id] ?? "")
                                                                : (asset.fa_cs_asset_number ?? "")
                                                        }
                                                        onChange={(e) => handleFacsNumberChange(asset.unique_id, e.target.value)}
                                                        title={asset.fa_cs_asset_number
                                                            ? `Explicit FA CS #: ${asset.fa_cs_asset_number}`
                                                            : `Auto-generated from "${asset.asset_id || 'row ' + asset.row_index}". Click to override.`
                                                        }
                                                    />
                                                </td>
                                            )}
                                            {/* Description - Editable */}
                                            <td className={cn(
                                                "text-slate-600 dark:text-slate-300",
                                                tableCompact ? "px-1 py-1" : "px-2 py-1.5"
                                            )}>
                                                <input
                                                    type="text"
                                                    className={cn(
                                                        "w-full border rounded truncate",
                                                        tableCompact ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm",
                                                        pendingDescriptions[asset.unique_id] !== undefined
                                                            ? "border-yellow-300 bg-yellow-50"
                                                            : "border-slate-200 bg-white hover:border-slate-300",
                                                        "focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                    )}
                                                    value={
                                                        pendingDescriptions[asset.unique_id] !== undefined
                                                            ? pendingDescriptions[asset.unique_id]
                                                            : (asset.description || "")
                                                    }
                                                    onChange={(e) => handleDescriptionChange(asset.unique_id, e.target.value)}
                                                    title={asset.description}
                                                />
                                            </td>
                                            {/* Cost - with gain/loss preview for disposals */}
                                            <td className={cn(
                                                "font-mono text-slate-600",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                <div className="flex flex-col">
                                                    {/* Option A2: For disposals show Cost (NBV: $X) + Proc → Gain/Loss */}
                                                    {isDisposal(asset.transaction_type) ? (
                                                        (() => {
                                                            const proceeds = asset.sale_proceeds || asset.proceeds || 0;
                                                            const accumDepr = asset.accumulated_depreciation || asset.accum_depr || 0;
                                                            const cost = asset.cost || 0;
                                                            const nbv = asset.net_book_value || (cost - accumDepr);
                                                            const gainLoss = asset.gain_loss ?? (proceeds - nbv);
                                                            const hasData = accumDepr > 0 || proceeds > 0;

                                                            // Build detailed tooltip
                                                            let tooltip = "═══ GAIN/LOSS CALCULATION ═══\n\n";
                                                            tooltip += `Cost:           $${cost.toLocaleString()}\n`;
                                                            tooltip += `- Accum Depr:   $${accumDepr.toLocaleString()}\n`;
                                                            tooltip += `────────────────────────\n`;
                                                            tooltip += `= NBV:          $${nbv.toLocaleString()}\n\n`;
                                                            tooltip += `Proceeds:       $${proceeds.toLocaleString()}\n`;
                                                            tooltip += `- NBV:          $${nbv.toLocaleString()}\n`;
                                                            tooltip += `────────────────────────\n`;
                                                            tooltip += `= ${gainLoss >= 0 ? 'GAIN' : 'LOSS'}:         $${Math.abs(gainLoss).toLocaleString()}`;

                                                            return (
                                                                <div className="cursor-help" title={tooltip}>
                                                                    {/* Line 1: Cost (NBV: $X) */}
                                                                    <span>
                                                                        ${cost.toLocaleString()}
                                                                        {hasData && (
                                                                            <span className="text-slate-400 text-[10px] ml-1">
                                                                                (NBV: ${nbv.toLocaleString()})
                                                                            </span>
                                                                        )}
                                                                    </span>
                                                                    {/* Line 2: Proc: $X → Gain/Loss */}
                                                                    {hasData && (
                                                                        <div className="text-[10px]">
                                                                            <span className="text-slate-500">Proc: ${proceeds.toLocaleString()}</span>
                                                                            <span className="text-slate-400 mx-1">→</span>
                                                                            <span className={gainLoss >= 0 ? "text-green-600" : "text-red-600"}>
                                                                                {gainLoss >= 0
                                                                                    ? `Gain: $${gainLoss.toLocaleString()}`
                                                                                    : `Loss: ($${Math.abs(gainLoss).toLocaleString()})`
                                                                                }
                                                                            </span>
                                                                        </div>
                                                                    )}
                                                                    {!hasData && (
                                                                        <div className="text-[10px] text-slate-400">
                                                                            Missing A/D & Proceeds
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            );
                                                        })()
                                                    ) : (
                                                        /* Editable cost input for non-disposals */
                                                        <input
                                                            type="number"
                                                            min="0"
                                                            step="0.01"
                                                            className={cn(
                                                                "w-full border rounded font-mono text-right",
                                                                tableCompact ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm",
                                                                pendingCosts[asset.unique_id] !== undefined
                                                                    ? "border-yellow-300 bg-yellow-50"
                                                                    : "border-slate-200 bg-white hover:border-slate-300",
                                                                "focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                            )}
                                                            value={
                                                                pendingCosts[asset.unique_id] !== undefined
                                                                    ? pendingCosts[asset.unique_id]
                                                                    : (asset.cost || 0)
                                                            }
                                                            onChange={(e) => handleCostChange(asset.unique_id, e.target.value)}
                                                            title={`Cost: $${(asset.cost || 0).toLocaleString()}`}
                                                        />
                                                    )}
                                                </div>
                                            </td>
                                            {/* Key Date - Context-aware based on transaction type - Editable */}
                                            <td className={cn(
                                                "text-slate-600",
                                                tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                            )}>
                                                {(() => {
                                                    // Determine which date to display based on transaction type
                                                    if (isDisposal(asset.transaction_type)) {
                                                        // Disposals: Show disposal date, with tooltip for original in-service
                                                        const disposalDate = asset.disposal_date || asset.disposed_date;
                                                        const isPriorYear = asset.transaction_type === TRANSACTION_TYPES.PRIOR_YEAR_DISPOSAL;
                                                        if (disposalDate) {
                                                            return (
                                                                <span
                                                                    className="group relative flex items-center gap-1 cursor-help"
                                                                    title={asset.in_service_date ? `Originally in service: ${asset.in_service_date}` : ""}
                                                                >
                                                                    <span className={isPriorYear ? "text-red-400" : "text-red-600"}>{disposalDate}</span>
                                                                    {asset.in_service_date && (
                                                                        <Info className={cn("w-3 h-3", isPriorYear ? "text-red-300" : "text-red-400")} />
                                                                    )}
                                                                </span>
                                                            );
                                                        }
                                                        // Fallback if no disposal date
                                                        return (
                                                            <span className="flex items-center gap-1 text-amber-600" title="Missing disposal date">
                                                                -
                                                                <AlertTriangle className="w-3.5 h-3.5" />
                                                            </span>
                                                        );
                                                    } else if (isTransfer(asset.transaction_type)) {
                                                        // Transfers: Show transfer date, with tooltip for original in-service
                                                        const transferDate = asset.transfer_date || asset.transferred_date;
                                                        const isPriorYear = asset.transaction_type === TRANSACTION_TYPES.PRIOR_YEAR_TRANSFER;
                                                        if (transferDate) {
                                                            return (
                                                                <span
                                                                    className="group relative flex items-center gap-1 cursor-help"
                                                                    title={asset.in_service_date ? `Originally in service: ${asset.in_service_date}` : ""}
                                                                >
                                                                    <span className={isPriorYear ? "text-purple-400" : "text-purple-600"}>{transferDate}</span>
                                                                    {asset.in_service_date && (
                                                                        <Info className={cn("w-3 h-3", isPriorYear ? "text-purple-300" : "text-purple-400")} />
                                                                    )}
                                                                </span>
                                                            );
                                                        }
                                                        // Fallback: Use in_service_date with note for transfers
                                                        if (asset.in_service_date) {
                                                            return (
                                                                <span className="text-slate-400" title="In-service date (transfer date not provided)">
                                                                    {asset.in_service_date}
                                                                </span>
                                                            );
                                                        }
                                                        return (
                                                            <span className="text-slate-400" title="No date - transfer of existing asset">
                                                                -
                                                            </span>
                                                        );
                                                    } else {
                                                        // Additions/Existing: Editable in-service date
                                                        const currentDate = pendingDates[asset.unique_id] !== undefined
                                                            ? pendingDates[asset.unique_id]
                                                            : (asset.in_service_date || asset.acquisition_date || "");
                                                        return (
                                                            <input
                                                                type="date"
                                                                className={cn(
                                                                    "border rounded",
                                                                    tableCompact ? "px-1 py-0.5 text-xs" : "px-1.5 py-1 text-sm",
                                                                    pendingDates[asset.unique_id] !== undefined
                                                                        ? "border-yellow-300 bg-yellow-50"
                                                                        : !currentDate
                                                                            ? "border-amber-300 bg-amber-50"
                                                                            : "border-slate-200 bg-white hover:border-slate-300",
                                                                    "focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                                )}
                                                                value={currentDate}
                                                                onChange={(e) => handleDateChange(asset.unique_id, e.target.value, 'in_service_date')}
                                                                title={currentDate ? `In Service: ${currentDate}` : "Missing date - click to add"}
                                                            />
                                                        );
                                                    }
                                                })()}
                                            </td>
                                            {/* Transaction Type - Dropdown */}
                                            <td className={tableCompact ? "px-1 py-1" : "px-2 py-1.5"}>
                                                <select
                                                    value={asset.transaction_type || ""}
                                                    onChange={(e) => handleTransactionTypeChange(asset.unique_id, e.target.value)}
                                                    className={cn(
                                                        "rounded font-medium whitespace-nowrap cursor-pointer border",
                                                        tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs",
                                                        asset.transaction_type === TRANSACTION_TYPES.ADDITION && !isDeMinimis && "bg-green-100 text-green-700 border-green-300",
                                                        asset.transaction_type === TRANSACTION_TYPES.ADDITION && isDeMinimis && "bg-emerald-100 text-emerald-700 border-emerald-300",
                                                        asset.transaction_type === TRANSACTION_TYPES.EXISTING && "bg-slate-100 text-slate-700 border-slate-300",
                                                        (asset.transaction_type === TRANSACTION_TYPES.CURRENT_YEAR_DISPOSAL ||
                                                         asset.transaction_type === TRANSACTION_TYPES.DISPOSAL) && "bg-red-100 text-red-700 border-red-300",
                                                        asset.transaction_type === TRANSACTION_TYPES.PRIOR_YEAR_DISPOSAL && "bg-red-50 text-red-400 border-red-200",
                                                        (asset.transaction_type === TRANSACTION_TYPES.CURRENT_YEAR_TRANSFER ||
                                                         asset.transaction_type === TRANSACTION_TYPES.TRANSFER) && "bg-purple-100 text-purple-700 border-purple-300",
                                                        asset.transaction_type === TRANSACTION_TYPES.PRIOR_YEAR_TRANSFER && "bg-purple-50 text-purple-400 border-purple-200",
                                                        !asset.transaction_type && "bg-yellow-100 text-yellow-700 border-yellow-300",
                                                        "focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                    )}
                                                    title="Change transaction type"
                                                >
                                                    <option value={TRANSACTION_TYPES.ADDITION}>Addition</option>
                                                    <option value={TRANSACTION_TYPES.EXISTING}>Existing</option>
                                                    <option value={TRANSACTION_TYPES.CURRENT_YEAR_DISPOSAL}>Disposal</option>
                                                    <option value={TRANSACTION_TYPES.CURRENT_YEAR_TRANSFER}>Transfer</option>
                                                </select>
                                            </td>

                                            {/* Class, Life, Method - Hidden for De Minimis, Disposals, and Transfers - Collapsible */}
                                            {showMacrsCols && (editingId === asset.unique_id ? (
                                                // Edit mode - Class, Life, Method inputs (hidden when not applicable)
                                                hideMacrsFields ? (
                                                    // De Minimis/Disposal/Transfer: Show empty cells (MACRS fields not applicable)
                                                    <>
                                                        <td className={cn("text-center text-slate-300", tableCompact ? "px-2 py-1.5" : "px-3 py-2.5")}>—</td>
                                                        <td className={cn("text-center text-slate-300", tableCompact ? "px-2 py-1.5" : "px-3 py-2.5")}>—</td>
                                                        <td className={cn("text-center text-slate-300", tableCompact ? "px-2 py-1.5" : "px-3 py-2.5")}>—</td>
                                                    </>
                                                ) : (
                                                    // MACRS/179/Bonus: Show edit inputs with dropdown for Class
                                                    <>
                                                        <td className={tableCompact ? "px-1 py-1" : "px-2 py-1.5"}>
                                                            <select
                                                                className={cn(
                                                                    "border rounded w-full",
                                                                    tableCompact ? "px-1 py-0.5 text-xs" : "px-1.5 py-1 text-sm"
                                                                )}
                                                                value={editForm.macrs_class || ""}
                                                                onChange={(e) => {
                                                                    const newClass = e.target.value;
                                                                    const classOption = MACRS_CLASS_OPTIONS.find(opt => opt.value === newClass);
                                                                    const newLife = classOption ? classOption.life : editForm.macrs_life;
                                                                    setEditForm({ ...editForm, macrs_class: newClass, macrs_life: newLife });
                                                                }}
                                                            >
                                                                <option value="">Select...</option>
                                                                {MACRS_CLASS_OPTIONS.map(opt => (
                                                                    <option key={opt.value} value={opt.value}>
                                                                        {opt.label}
                                                                    </option>
                                                                ))}
                                                            </select>
                                                        </td>
                                                        <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                            <input
                                                                type="number"
                                                                className={cn(
                                                                    "border rounded w-14",
                                                                    tableCompact ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm"
                                                                )}
                                                                value={editForm.macrs_life}
                                                                onChange={(e) => setEditForm({ ...editForm, macrs_life: e.target.value })}
                                                            />
                                                        </td>
                                                        <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                            <select
                                                                className={cn(
                                                                    "border rounded w-full",
                                                                    tableCompact ? "px-1 py-0.5 text-xs" : "px-1.5 py-1 text-sm"
                                                                )}
                                                                value={editForm.macrs_method || ""}
                                                                onChange={(e) => setEditForm({ ...editForm, macrs_method: e.target.value })}
                                                            >
                                                                <option value="200DB">200DB</option>
                                                                <option value="150DB">150DB</option>
                                                                <option value="SL">SL</option>
                                                                <option value="ADS">ADS</option>
                                                            </select>
                                                        </td>
                                                    </>
                                                )
                                            ) : (
                                                // Display mode - Class, Life, Method display (hidden when not applicable)
                                                hideMacrsFields ? (
                                                    // De Minimis/Disposal/Transfer: Show empty cells with tooltip
                                                    <>
                                                        <td className={cn("text-center", tableCompact ? "px-2 py-1.5" : "px-3 py-2.5")}>
                                                            <span className="text-slate-300 cursor-help" title={isDeMinimis ? "De Minimis assets are expensed, not depreciated" : "Classification not required for disposals/transfers"}>—</span>
                                                        </td>
                                                        <td className={cn("text-center", tableCompact ? "px-2 py-1.5" : "px-3 py-2.5")}>
                                                            <span className="text-slate-300 cursor-help" title={isDeMinimis ? "De Minimis assets are expensed, not depreciated" : "Classification not required for disposals/transfers"}>—</span>
                                                        </td>
                                                        <td className={cn("text-center", tableCompact ? "px-2 py-1.5" : "px-3 py-2.5")}>
                                                            <span className="text-slate-300 cursor-help" title={isDeMinimis ? "De Minimis assets are expensed, not depreciated" : "Classification not required for disposals/transfers"}>—</span>
                                                        </td>
                                                    </>
                                                ) : (
                                                    // MACRS/179/Bonus: Show classification data with editable Class dropdown
                                                    <>
                                                        <td className={tableCompact ? "px-1 py-1" : "px-2 py-1.5"}>
                                                            <select
                                                                value={asset.macrs_class || ""}
                                                                onChange={(e) => handleMacrsClassChange(asset.unique_id, e.target.value)}
                                                                className={cn(
                                                                    "bg-blue-50 text-blue-700 rounded font-semibold border border-blue-200 cursor-pointer w-full",
                                                                    tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs",
                                                                    "focus:outline-none focus:ring-1 focus:ring-blue-500"
                                                                )}
                                                                title={asset.fa_cs_wizard_category ? `FA CS: ${asset.fa_cs_wizard_category}` : "Select asset class"}
                                                            >
                                                                <option value="">Select...</option>
                                                                {MACRS_CLASS_OPTIONS.map(opt => (
                                                                    <option key={opt.value} value={opt.value}>
                                                                        {opt.label}
                                                                    </option>
                                                                ))}
                                                            </select>
                                                        </td>
                                                        <td className={cn(
                                                            "text-slate-600 text-center",
                                                            tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"
                                                        )}>{asset.macrs_life ? `${asset.macrs_life} yr` : "-"}</td>
                                                        <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                            <span className={cn(
                                                                "bg-slate-100 text-slate-700 rounded font-mono font-medium border border-slate-200",
                                                                tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs"
                                                            )}>
                                                                {asset.macrs_method || "N/A"}
                                                            </span>
                                                        </td>
                                                    </>
                                                )
                                            ))}

                                            {/* Election Column - 179/Bonus/DeMinimis/MACRS - Collapsible */}
                                            {showMacrsCols && (
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                {asset.transaction_type === "Current Year Addition" ? (
                                                    <div className="relative flex items-center gap-1">
                                                        <select
                                                            value={asset.depreciation_election || "MACRS"}
                                                            onChange={(e) => handleElectionChange(asset.unique_id, e.target.value)}
                                                            className={cn(
                                                                "rounded border font-medium cursor-pointer",
                                                                tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs",
                                                                // De Minimis with cost warning
                                                                asset.depreciation_election === "DeMinimis" && asset.cost > DE_MINIMIS_THRESHOLD
                                                                    ? "bg-orange-100 text-orange-700 border-orange-400"
                                                                    : asset.depreciation_election === "DeMinimis" && "bg-green-100 text-green-700 border-green-300",
                                                                // Bonus on real property warning
                                                                asset.depreciation_election === "Bonus" && isRealProperty(asset.macrs_life)
                                                                    ? "bg-red-100 text-red-700 border-red-400"
                                                                    : asset.depreciation_election === "Bonus" && "bg-purple-100 text-purple-700 border-purple-300",
                                                                asset.depreciation_election === "Section179" && "bg-blue-100 text-blue-700 border-blue-300",
                                                                (!asset.depreciation_election || asset.depreciation_election === "MACRS") && "bg-slate-100 text-slate-700 border-slate-300",
                                                                asset.depreciation_election === "ADS" && "bg-slate-100 text-slate-700 border-slate-300"
                                                            )}
                                                        >
                                                            <option value="MACRS">MACRS</option>
                                                            <option value="DeMinimis">De Minimis</option>
                                                            <option value="Section179">§179</option>
                                                            <option value="Bonus">Bonus</option>
                                                            <option value="ADS">ADS</option>
                                                        </select>
                                                        {/* Warning icon for De Minimis over threshold */}
                                                        {asset.depreciation_election === "DeMinimis" && asset.cost > DE_MINIMIS_THRESHOLD && (
                                                            <AlertTriangle className="w-3.5 h-3.5 text-orange-500" title={`Cost $${asset.cost.toLocaleString()} exceeds De Minimis threshold of $${DE_MINIMIS_THRESHOLD.toLocaleString()}`} />
                                                        )}
                                                        {/* Warning icon for Bonus on real property */}
                                                        {asset.depreciation_election === "Bonus" && isRealProperty(asset.macrs_life) && (
                                                            <AlertTriangle className="w-3.5 h-3.5 text-red-500" title="Real property (27.5/39 year) cannot take bonus depreciation" />
                                                        )}
                                                        {/* Info icon with Radix UI tooltip for proper multi-line display */}
                                                        <Tooltip>
                                                            <TooltipTrigger asChild>
                                                                <Info
                                                                    className={cn(
                                                                        "cursor-help",
                                                                        tableCompact ? "w-3 h-3" : "w-3.5 h-3.5",
                                                                        asset.depreciation_election === "DeMinimis" ? "text-green-500" :
                                                                        asset.depreciation_election === "Section179" ? "text-blue-500" :
                                                                        asset.depreciation_election === "Bonus" ? "text-purple-500" : "text-slate-400"
                                                                    )}
                                                                />
                                                            </TooltipTrigger>
                                                            <TooltipContent side="left" className="max-w-xs">
                                                                {asset.depreciation_election === "DeMinimis" ? (
                                                                    <div className="space-y-1">
                                                                        <div className="font-semibold text-green-300">De Minimis Safe Harbor</div>
                                                                        <div>• Expense immediately (≤${DE_MINIMIS_THRESHOLD.toLocaleString()})</div>
                                                                        <div>• NOT added to FA CS</div>
                                                                        <div>• Exported to separate sheet</div>
                                                                        {asset.cost > DE_MINIMIS_THRESHOLD && (
                                                                            <div className="text-orange-300 font-medium">⚠ Cost ${asset.cost.toLocaleString()} exceeds threshold!</div>
                                                                        )}
                                                                    </div>
                                                                ) : asset.depreciation_election === "Section179" ? (
                                                                    <div className="space-y-1">
                                                                        <div className="font-semibold text-blue-300">§179 Expense Election</div>
                                                                        <div>• Full deduction in Year 1</div>
                                                                        <div>• Subject to business income limit</div>
                                                                        <div>• {taxYear} limit: ${currentYearConfig.section179Limit.toLocaleString()}</div>
                                                                    </div>
                                                                ) : asset.depreciation_election === "Bonus" ? (
                                                                    <div className="space-y-1">
                                                                        <div className="font-semibold text-purple-300">Bonus Depreciation</div>
                                                                        <div>• {currentYearConfig.bonusPercent}% deduction in Year 1 ({taxYear})</div>
                                                                        <div>• Remaining {100 - currentYearConfig.bonusPercent}% via MACRS</div>
                                                                        <div>• No income limitation</div>
                                                                        {isRealProperty(asset.macrs_life) && (
                                                                            <div className="text-red-300 font-medium">⚠ Real property cannot take bonus!</div>
                                                                        )}
                                                                    </div>
                                                                ) : asset.depreciation_election === "ADS" ? (
                                                                    <div className="space-y-1">
                                                                        <div className="font-semibold text-slate-300">Alternative Depreciation (ADS)</div>
                                                                        <div>• Straight-line method</div>
                                                                        <div>• Longer recovery periods</div>
                                                                        <div>• Required for some property</div>
                                                                    </div>
                                                                ) : (
                                                                    <div className="space-y-1">
                                                                        <div className="font-semibold text-slate-300">MACRS (Default)</div>
                                                                        <div>• Standard depreciation</div>
                                                                        <div>• 200DB or 150DB method</div>
                                                                        <div>• Based on property class</div>
                                                                    </div>
                                                                )}
                                                            </TooltipContent>
                                                        </Tooltip>
                                                    </div>
                                                ) : (
                                                    <span className={cn(
                                                        "bg-slate-50 text-slate-400 rounded",
                                                        tableCompact ? "px-1 py-0.5 text-[10px]" : "px-1.5 py-0.5 text-xs"
                                                    )}>
                                                        N/A
                                                    </span>
                                                )}
                                            </td>
                                            )}

                                            {/* Actions */}
                                            <td className={tableCompact ? "px-2 py-1.5" : "px-3 py-2.5"}>
                                                <div className="flex gap-0.5">
                                                    {editingId === asset.unique_id ? (
                                                        <>
                                                            <button onClick={() => handleSave(asset.unique_id)} className={cn(
                                                                "hover:bg-green-100 text-green-600 rounded",
                                                                tableCompact ? "p-1" : "p-1.5"
                                                            )}>
                                                                <Save className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                            </button>
                                                            <button onClick={() => setEditingId(null)} className={cn(
                                                                "hover:bg-red-100 text-red-600 rounded",
                                                                tableCompact ? "p-1" : "p-1.5"
                                                            )}>
                                                                <X className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                            </button>
                                                        </>
                                                    ) : (
                                                        <>
                                                            {!isApproved && !hasErrors && (
                                                                <button
                                                                    onClick={() => handleApprove(asset.unique_id)}
                                                                    className={cn(
                                                                        "hover:bg-green-100 text-green-600 rounded",
                                                                        tableCompact ? "p-1" : "p-1.5"
                                                                    )}
                                                                    title="Approve"
                                                                >
                                                                    <Check className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                                </button>
                                                            )}
                                                            <button
                                                                onClick={() => handleEditClick(asset)}
                                                                className={cn(
                                                                    "hover:bg-slate-100 text-slate-600 rounded",
                                                                    tableCompact ? "p-1" : "p-1.5"
                                                                )}
                                                                title="Edit"
                                                            >
                                                                <Edit2 className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                            </button>
                                                            <button
                                                                onClick={() => handleRemove(asset.unique_id, asset.description)}
                                                                className={cn(
                                                                    "hover:bg-red-100 text-red-500 rounded",
                                                                    tableCompact ? "p-1" : "p-1.5"
                                                                )}
                                                                title="Remove from import"
                                                            >
                                                                <Trash2 className={tableCompact ? "w-3.5 h-3.5" : "w-4 h-4"} />
                                                            </button>
                                                        </>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Footer */}
            <div className="mt-4 text-sm text-slate-500 text-center">
                Showing {filteredAssets.length} of {showExistingAssets ? stats.total : stats.actionable} {showExistingAssets ? 'total' : 'actionable'} assets
                {!showExistingAssets && stats.existing > 0 && (
                    <span className="text-slate-400 ml-1">
                        ({stats.existing} existing assets hidden)
                    </span>
                )}
                {(filter !== 'all' || !showExistingAssets) && (
                    <button
                        onClick={() => { setFilter('all'); setShowExistingAssets(true); }}
                        className="ml-2 text-blue-600 hover:underline"
                    >
                        Show all {stats.total}
                    </button>
                )}
            </div>

            {/* FA CS Compatibility Check Dialog */}
            {showCompatDialog && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
                        {/* Dialog Header */}
                        <div className="p-6 border-b">
                            <div className="flex items-center gap-3">
                                <div className={cn(
                                    "h-10 w-10 rounded-full flex items-center justify-center",
                                    compatibilityCheck?.is_compatible
                                        ? "bg-green-100"
                                        : "bg-yellow-100"
                                )}>
                                    {compatibilityCheck?.is_compatible ? (
                                        <CheckCircle className="h-5 w-5 text-green-600" />
                                    ) : (
                                        <AlertTriangle className="h-5 w-5 text-yellow-600" />
                                    )}
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold">
                                        {compatibilityCheck?.is_compatible
                                            ? "Ready for FA CS Export"
                                            : "FA CS Compatibility Issues Found"
                                        }
                                    </h2>
                                    <p className="text-sm text-muted-foreground">
                                        {compatibilityCheck?.is_compatible
                                            ? "All assets passed validation checks"
                                            : `${compatibilityCheck?.issues?.length || 0} issues need attention`
                                        }
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* 179/Bonus Depreciation Preview */}
                        {depreciationPreview && (
                            <div className="p-6 bg-gradient-to-r from-blue-50 to-indigo-50 border-b">
                                <div className="flex items-center gap-2 mb-3">
                                    <Calculator className="h-5 w-5 text-blue-600" />
                                    <h3 className="font-semibold text-blue-900">Year 1 Depreciation Preview</h3>
                                </div>
                                <p className="text-xs text-blue-700 mb-3">
                                    Based on current elections, FA CS will calculate:
                                </p>
                                <div className="grid grid-cols-4 gap-3">
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-xs text-slate-500 mb-1">De Minimis Expense</div>
                                        <div className="text-lg font-bold text-emerald-600">
                                            ${(depreciationPreview.de_minimis || 0).toLocaleString()}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-xs text-slate-500 mb-1">Section 179</div>
                                        <div className="text-lg font-bold text-green-600">
                                            ${(depreciationPreview.section_179 || 0).toLocaleString()}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-xs text-slate-500 mb-1">Bonus ({Math.round((depreciationPreview.bonus_rate || 0.6) * 100)}%)</div>
                                        <div className="text-lg font-bold text-purple-600">
                                            ${(depreciationPreview.bonus || 0).toLocaleString()}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 shadow-sm">
                                        <div className="text-xs text-slate-500 mb-1">Regular MACRS</div>
                                        <div className="text-lg font-bold text-slate-700">
                                            ${(depreciationPreview.regular_macrs || 0).toLocaleString()}
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-3 pt-3 border-t border-blue-200">
                                    <div className="flex justify-between items-center">
                                        <span className="text-sm font-medium text-blue-900">Total Year 1 Deductions</span>
                                        <span className="text-xl font-bold text-blue-600">
                                            ${(depreciationPreview.total_year1 || 0).toLocaleString()}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Compatibility Issues */}
                        {compatibilityCheck?.issues?.length > 0 && (
                            <div className="p-6">
                                <div className="flex items-center justify-between mb-4">
                                    <h3 className="font-semibold">Issues to Review</h3>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={autoFixCompatibilityIssues}
                                        className="text-blue-600"
                                    >
                                        <Wand2 className="h-4 w-4 mr-1" />
                                        Auto-Fix All
                                    </Button>
                                </div>
                                <div className="space-y-2 max-h-60 overflow-y-auto">
                                    {compatibilityCheck.issues.map((issue, idx) => (
                                        <div
                                            key={idx}
                                            className={cn(
                                                "p-3 rounded-lg border text-sm",
                                                issue.severity === 'error'
                                                    ? "bg-red-50 border-red-200"
                                                    : "bg-yellow-50 border-yellow-200"
                                            )}
                                        >
                                            <div className="flex items-start gap-2">
                                                {issue.severity === 'error' ? (
                                                    <X className="h-4 w-4 text-red-500 mt-0.5" />
                                                ) : (
                                                    <AlertTriangle className="h-4 w-4 text-yellow-500 mt-0.5" />
                                                )}
                                                <div className="flex-1">
                                                    <div className="font-medium">{issue.asset_id}</div>
                                                    <div className="text-muted-foreground">{issue.message}</div>
                                                    {issue.suggestion && (
                                                        <div className="text-xs text-blue-600 mt-1">
                                                            Suggestion: {issue.suggestion}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Dialog Actions */}
                        <div className="p-6 border-t bg-slate-50 flex justify-end gap-3">
                            <Button
                                variant="outline"
                                onClick={() => setShowCompatDialog(false)}
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={() => {
                                    setShowCompatDialog(false);
                                    handleExport();
                                }}
                                disabled={!compatibilityCheck?.is_compatible}
                                className={cn(
                                    "text-white",
                                    compatibilityCheck?.is_compatible
                                        ? "bg-green-600 hover:bg-green-700"
                                        : "bg-gray-400 cursor-not-allowed"
                                )}
                            >
                                <Download className="w-4 h-4 mr-2" />
                                {compatibilityCheck?.is_compatible
                                    ? "Export Now"
                                    : "Fix Issues First"
                                }
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
        </TooltipProvider>
    );
}

export { Review };
export default Review;
