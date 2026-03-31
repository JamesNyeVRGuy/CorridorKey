<script lang="ts">
	import { currentJob, runningJobs, queuedJobs, jobHistory, refreshJobs, clearDismissed } from '$lib/stores/jobs';
	import { api } from '$lib/api';
	import type { Job } from '$lib/api';
	import { getStoredUser } from '$lib/auth';
	import JobRow from '../../components/JobRow.svelte';
	import ProgressBar from '../../components/ProgressBar.svelte';

	let cancelling = $state(false);
	let expandedGroups = $state<Set<string>>(new Set());
	let activeTab = $state<'running' | 'queue' | 'history'>('running');

	// Filters
	let searchQuery = $state('');
	let typeFilter = $state('all');
	let statusFilter = $state('all');  // for history tab

	// Admin org filter
	const user = getStoredUser();
	const isAdmin = user?.tier === 'platform_admin';
	let orgFilter = $state('all');
	let orgList = $state<{ org_id: string; name: string }[]>([]);

	// Load orgs for admin filter
	if (isAdmin) {
		fetch('/api/admin/orgs', {
			headers: { 'Authorization': `Bearer ${localStorage.getItem('ck:auth_token')}` }
		}).then(r => r.json()).then(data => {
			orgList = data.orgs ?? [];
		}).catch(() => {});
	}

	// Auto-switch to running tab when jobs start
	$effect(() => {
		if ($runningJobs.length > 0 && activeTab !== 'running') {
			// Don't auto-switch if user is actively browsing another tab
		}
	});

	async function cancelAll() {
		cancelling = true;
		try {
			await api.jobs.cancelAll();
			await refreshJobs();
		} finally {
			cancelling = false;
		}
	}

	function toggleGroup(groupId: string) {
		const next = new Set(expandedGroups);
		if (next.has(groupId)) next.delete(groupId);
		else next.add(groupId);
		expandedGroups = next;
	}

	interface ShardGroup {
		group_id: string;
		clip_name: string;
		shards: Job[];
		current_frame: number;
		total_frames: number;
		completed: number;
		running: number;
		failed: number;
	}

	function groupShards(jobs: Job[]): (Job | ShardGroup)[] {
		const seen = new Set<string>();
		const deduped: Job[] = [];
		for (const job of jobs) {
			if (!seen.has(job.id)) {
				seen.add(job.id);
				deduped.push(job);
			}
		}
		const groups = new Map<string, Job[]>();
		const singles: Job[] = [];
		for (const job of deduped) {
			if (job.shard_group && job.shard_total > 1) {
				const list = groups.get(job.shard_group) ?? [];
				list.push(job);
				groups.set(job.shard_group, list);
			} else {
				singles.push(job);
			}
		}
		const result: (Job | ShardGroup)[] = [];
		for (const [group_id, shards] of groups) {
			result.push({
				group_id,
				clip_name: shards[0].clip_name,
				shards: shards.sort((a, b) => a.shard_index - b.shard_index),
				current_frame: shards.reduce((s, j) => s + j.current_frame, 0),
				total_frames: shards.reduce((s, j) => s + j.total_frames, 0),
				completed: shards.filter((j) => j.status === 'completed').length,
				running: shards.filter((j) => j.status === 'running').length,
				failed: shards.filter((j) => j.status === 'failed').length,
			});
		}
		result.push(...singles);
		return result;
	}

	function isShardGroup(item: Job | ShardGroup): item is ShardGroup {
		return 'group_id' in item;
	}

	function matchesFilters(job: Job): boolean {
		if (searchQuery) {
			const q = searchQuery.toLowerCase();
			if (!job.clip_name.toLowerCase().includes(q) && !job.id.toLowerCase().includes(q)) return false;
		}
		if (typeFilter !== 'all' && job.job_type !== typeFilter) return false;
		if (activeTab === 'history' && statusFilter !== 'all' && job.status !== statusFilter) return false;
		if (isAdmin && orgFilter !== 'all' && job.org_id !== orgFilter) return false;
		return true;
	}

	let filteredRunning = $derived(groupShards($runningJobs.filter(matchesFilters)));
	let filteredQueued = $derived(groupShards($queuedJobs.filter(matchesFilters)));
	let filteredHistory = $derived(groupShards($jobHistory.filter(matchesFilters)));

	let hasActive = $derived($runningJobs.length > 0 || $queuedJobs.length > 0);

	const jobTypes = [
		{ value: 'all', label: 'All types' },
		{ value: 'inference', label: 'Inference' },
		{ value: 'gvm_alpha', label: 'GVM Alpha' },
		{ value: 'videomama_alpha', label: 'VideoMaMa' },
		{ value: 'video_extract', label: 'Extract' },
		{ value: 'video_stitch', label: 'Stitch' },
		{ value: 'preview_reprocess', label: 'Preview' },
	];
</script>

<svelte:head>
	<title>Jobs — CorridorKey</title>
</svelte:head>

<div class="page">
	<div class="page-header">
		<h1 class="page-title">Jobs</h1>
		<div class="header-actions">
			<button class="btn-ghost" onclick={() => refreshJobs()}>
				<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
					<path d="M12 7a5 5 0 11-1.5-3.5M12 2v3h-3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
				</svg>
				Refresh
			</button>
			{#if hasActive}
				<button class="btn-ghost btn-danger" onclick={cancelAll} disabled={cancelling}>Cancel All</button>
			{/if}
		</div>
	</div>

	<!-- Tabs -->
	<div class="tabs">
		<button class="tab mono" class:active={activeTab === 'running'} onclick={() => activeTab = 'running'}>
			Running
			{#if $runningJobs.length > 0}<span class="tab-badge">{$runningJobs.length}</span>{/if}
		</button>
		<button class="tab mono" class:active={activeTab === 'queue'} onclick={() => activeTab = 'queue'}>
			Queue
			{#if $queuedJobs.length > 0}<span class="tab-badge">{$queuedJobs.length}</span>{/if}
		</button>
		<button class="tab mono" class:active={activeTab === 'history'} onclick={() => activeTab = 'history'}>
			History
			{#if $jobHistory.length > 0}<span class="tab-badge">{$jobHistory.length}</span>{/if}
		</button>
	</div>

	<!-- Filter bar -->
	<div class="filter-bar">
		<input type="text" class="filter-search mono" placeholder="Search clip name or job ID..." bind:value={searchQuery} />
		<select class="filter-select mono" bind:value={typeFilter}>
			{#each jobTypes as t}
				<option value={t.value}>{t.label}</option>
			{/each}
		</select>
		{#if activeTab === 'history'}
			<select class="filter-select mono" bind:value={statusFilter}>
				<option value="all">All statuses</option>
				<option value="completed">Completed</option>
				<option value="failed">Failed</option>
				<option value="cancelled">Cancelled</option>
			</select>
		{/if}
		{#if isAdmin && orgList.length > 0}
			<select class="filter-select mono" bind:value={orgFilter}>
				<option value="all">All orgs</option>
				{#each orgList as org}
					<option value={org.org_id}>{org.name}</option>
				{/each}
			</select>
		{/if}
	</div>

	<!-- Tab content -->
	{#if activeTab === 'running'}
		{#if filteredRunning.length > 0}
			<div class="job-list">
				{#each filteredRunning as item}
					{#if isShardGroup(item)}
						{@const g = item}
						<button class="shard-group" onclick={() => toggleGroup(g.group_id)} aria-expanded={expandedGroups.has(g.group_id)}>
							<div class="shard-group-header">
								<span class="type-dot" style="background: var(--state-running); box-shadow: 0 0 6px var(--state-running)"></span>
								<span class="shard-group-label mono">SHARDED</span>
								<span class="shard-group-clip">{g.clip_name}</span>
								<span class="shard-group-info mono">{g.completed}/{g.shards.length} GPUs done</span>
								<span class="shard-group-expand mono">{expandedGroups.has(g.group_id) ? '▲' : '▼'}</span>
							</div>
							<ProgressBar current={g.current_frame} total={g.total_frames} />
						</button>
						{#if expandedGroups.has(g.group_id)}
							{#each g.shards as job (job.id)}
								<JobRow {job} showCancel />
							{/each}
						{/if}
					{:else}
						<JobRow job={item} showCancel />
					{/if}
				{/each}
			</div>
		{:else}
			<div class="empty-tab">
				<p class="empty-text mono">No running jobs</p>
			</div>
		{/if}

	{:else if activeTab === 'queue'}
		{#if filteredQueued.length > 0}
			<div class="job-list">
				{#each filteredQueued as item, i}
					{#if isShardGroup(item)}
						{@const g = item}
						<button class="shard-group" onclick={() => toggleGroup(g.group_id)} aria-expanded={expandedGroups.has(g.group_id)}>
							<div class="shard-group-header">
								<span class="type-dot" style="background: var(--state-queued)"></span>
								<span class="shard-group-label mono">SHARDED</span>
								<span class="shard-group-clip">{g.clip_name}</span>
								<span class="shard-group-info mono">{g.shards.length} shards queued</span>
								<span class="shard-group-expand mono">{expandedGroups.has(g.group_id) ? '▲' : '▼'}</span>
							</div>
						</button>
						{#if expandedGroups.has(g.group_id)}
							{#each g.shards as job, j (job.id)}
								<JobRow {job} showCancel queueIndex={j} />
							{/each}
						{/if}
					{:else}
						<JobRow job={item} showCancel queueIndex={i} />
					{/if}
				{/each}
			</div>
		{:else}
			<div class="empty-tab">
				<p class="empty-text mono">Queue is empty</p>
			</div>
		{/if}

	{:else if activeTab === 'history'}
		<div class="history-header">
			<button class="clear-btn mono" onclick={clearDismissed}>SHOW ALL</button>
		</div>
		{#if filteredHistory.length > 0}
			<div class="job-list">
				{#each filteredHistory as item}
					{#if isShardGroup(item)}
						{@const g = item}
						<button class="shard-group" onclick={() => toggleGroup(g.group_id)} aria-expanded={expandedGroups.has(g.group_id)}>
							<div class="shard-group-header">
								<span class="type-dot" style="background: {g.failed > 0 ? 'var(--state-failed)' : 'var(--state-complete)'}"></span>
								<span class="shard-group-label mono">SHARDED</span>
								<span class="shard-group-clip">{g.clip_name}</span>
								<span class="shard-group-info mono">{g.completed}/{g.shards.length} done{g.failed > 0 ? `, ${g.failed} failed` : ''}</span>
								<span class="shard-group-expand mono">{expandedGroups.has(g.group_id) ? '▲' : '▼'}</span>
							</div>
						</button>
						{#if expandedGroups.has(g.group_id)}
							{#each g.shards as job (job.id)}
								<JobRow {job} showDismiss />
							{/each}
						{/if}
					{:else}
						<JobRow job={item} showDismiss />
					{/if}
				{/each}
			</div>
		{:else}
			<div class="empty-tab">
				<p class="empty-text mono">No job history</p>
			</div>
		{/if}
	{/if}
</div>

<style>
	.page {
		padding: var(--sp-5) var(--sp-6);
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
	}

	.page-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.page-title {
		font-family: var(--font-sans);
		font-size: 20px;
		font-weight: 700;
		letter-spacing: -0.01em;
	}

	.header-actions {
		display: flex;
		gap: var(--sp-2);
	}

	.btn-ghost {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-2) var(--sp-3);
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 6px;
		cursor: pointer;
		transition: all 0.15s;
	}
	.btn-ghost:hover { color: var(--text-primary); border-color: var(--text-tertiary); background: var(--surface-2); }
	.btn-ghost:disabled { opacity: 0.5; cursor: not-allowed; }
	.btn-danger { color: var(--state-error); border-color: rgba(255, 82, 82, 0.3); }
	.btn-danger:hover { color: var(--state-error) !important; background: rgba(255, 82, 82, 0.08) !important; border-color: rgba(255, 82, 82, 0.5) !important; }

	/* Tabs */
	.tabs {
		display: flex;
		gap: 0;
		border-bottom: 1px solid var(--border);
	}

	.tab {
		padding: var(--sp-2) var(--sp-4);
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.06em;
		color: var(--text-tertiary);
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		cursor: pointer;
		transition: all 0.15s;
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}
	.tab:hover { color: var(--text-secondary); }
	.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

	.tab-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		font-size: 10px;
		background: var(--surface-4);
		border-radius: 9px;
		color: var(--text-secondary);
	}
	.tab.active .tab-badge { background: rgba(255, 242, 3, 0.15); color: var(--accent); }

	/* Filter bar */
	.filter-bar {
		display: flex;
		gap: var(--sp-2);
		align-items: center;
	}

	.filter-search {
		flex: 1;
		padding: 7px 10px;
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 12px;
		outline: none;
	}
	.filter-search:focus { border-color: var(--accent); }
	.filter-search::placeholder { color: var(--text-tertiary); }

	.filter-select {
		padding: 7px 10px;
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 12px;
	}

	/* Job list */
	.job-list {
		border: 1px solid var(--border);
		border-radius: 8px;
		overflow: hidden;
		background: var(--surface-1);
	}

	.shard-group {
		display: block;
		width: 100%;
		text-align: left;
		font: inherit;
		color: inherit;
		padding: var(--sp-3) var(--sp-4);
		border: none;
		border-bottom: 1px solid var(--border-subtle);
		cursor: pointer;
		transition: background 0.15s;
		background: linear-gradient(90deg, rgba(0, 154, 218, 0.04), transparent);
		border-left: 3px solid var(--secondary);
	}
	.shard-group:hover { background: var(--surface-2); }

	.shard-group-header {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		margin-bottom: var(--sp-2);
	}

	.type-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

	.shard-group-label {
		font-size: 9px; font-weight: 600; color: var(--secondary);
		padding: 1px 5px; border: 1px solid var(--secondary-muted); border-radius: 3px; letter-spacing: 0.06em;
	}
	.shard-group-clip { font-size: 13px; font-weight: 600; color: var(--text-primary); }
	.shard-group-info { margin-left: auto; font-size: 10px; color: var(--text-secondary); }
	.shard-group-expand { font-size: 9px; color: var(--text-tertiary); margin-left: var(--sp-1); }

	/* History header */
	.history-header {
		display: flex;
		justify-content: flex-end;
	}

	.clear-btn {
		font-size: 9px; letter-spacing: 0.06em; color: var(--text-tertiary);
		background: transparent; border: 1px solid var(--border); border-radius: 4px;
		padding: 4px 8px; cursor: pointer; transition: color 0.15s;
	}
	.clear-btn:hover { color: var(--text-secondary); }

	/* Empty state */
	.empty-tab {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--sp-8) 0;
	}
	.empty-text { font-size: 13px; color: var(--text-tertiary); }
</style>
