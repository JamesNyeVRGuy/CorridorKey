<script lang="ts">
	import { onMount } from 'svelte';
	import { loadUserOrgs } from '$lib/stores/orgs';
	import { getStoredUser } from '$lib/auth';

	interface OrgInfo {
		org_id: string;
		name: string;
		owner_id: string;
		personal: boolean;
		created_at: number;
	}

	let orgs = $state<OrgInfo[]>([]);
	let loading = $state(true);
	let newOrgName = $state('');
	let creating = $state(false);
	let createError = $state('');

	// Per-org stats (loaded in parallel)
	let orgCredits = $state<Map<string, { balance_seconds: number }>>(new Map());
	let orgStorage = $state<Map<string, { used_gb: number; quota_gb: number; percent_used: number }>>(new Map());
	let orgMembers = $state<Map<string, number>>(new Map());

	const userId = getStoredUser()?.id ?? '';

	async function authFetch(path: string, opts?: RequestInit) {
		const token = localStorage.getItem('ck:auth_token');
		const headers: Record<string, string> = { 'Content-Type': 'application/json' };
		if (token) headers['Authorization'] = `Bearer ${token}`;
		const res = await fetch(path, { ...opts, headers });
		if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
		return res.json();
	}

	async function loadOrgs() {
		try {
			const res = await authFetch('/api/orgs');
			orgs = res.orgs;
			// Load stats for each org in parallel
			for (const org of orgs) {
				authFetch(`/api/orgs/${org.org_id}/credits`).then(c => {
					orgCredits = new Map(orgCredits).set(org.org_id, c);
				}).catch(() => {});
				authFetch(`/api/orgs/${org.org_id}/storage`).then(s => {
					orgStorage = new Map(orgStorage).set(org.org_id, s);
				}).catch(() => {});
				authFetch(`/api/orgs/${org.org_id}/members`).then(m => {
					orgMembers = new Map(orgMembers).set(org.org_id, m.members?.length ?? 0);
				}).catch(() => {});
			}
		} catch { orgs = []; }
	}

	async function createOrg() {
		if (!newOrgName.trim()) return;
		creating = true; createError = '';
		try {
			await authFetch('/api/orgs', { method: 'POST', body: JSON.stringify({ name: newOrgName.trim() }) });
			newOrgName = '';
			await loadOrgs();
			loadUserOrgs();
		} catch (e) {
			createError = e instanceof Error ? e.message : 'Failed';
		} finally { creating = false; }
	}

	function isOwner(org: OrgInfo): boolean { return org.owner_id === userId; }

	onMount(async () => {
		await loadOrgs();
		loading = false;
	});
</script>

<svelte:head>
	<title>Organizations — CorridorKey</title>
</svelte:head>

<div class="page">
	<div class="page-header">
		<h1 class="page-title">Organizations</h1>
	</div>

	<!-- Create org -->
	<div class="create-bar">
		<input type="text" class="input mono" bind:value={newOrgName} placeholder="New organization name..." />
		<button class="btn-primary mono" onclick={createOrg} disabled={creating || !newOrgName.trim()}>
			{creating ? 'Creating...' : '+ Create'}
		</button>
		{#if createError}<span class="error-text mono">{createError}</span>{/if}
	</div>

	{#if loading}
		<div class="loading mono">Loading...</div>
	{:else if orgs.length === 0}
		<div class="empty-state">
			<p class="empty-text">No organizations yet</p>
			<p class="empty-hint mono">Create one above to get started.</p>
		</div>
	{:else}
		<div class="org-grid">
			{#each orgs as org (org.org_id)}
				{@const credits = orgCredits.get(org.org_id)}
				{@const storage = orgStorage.get(org.org_id)}
				{@const memberCount = orgMembers.get(org.org_id) ?? 0}
				<a href="/orgs/{org.org_id}" class="org-card">
					<div class="card-top">
						<span class="org-name">{org.name}</span>
						<div class="card-badges">
							{#if org.personal}
								<span class="badge personal mono">PERSONAL</span>
							{:else}
								<span class="badge team mono">TEAM</span>
							{/if}
							{#if isOwner(org)}
								<span class="badge owner mono">OWNER</span>
							{/if}
						</div>
					</div>
					<div class="card-stats">
						<span class="card-stat mono">{memberCount} member{memberCount !== 1 ? 's' : ''}</span>
						{#if credits}
							{@const hrs = credits.balance_seconds / 3600}
							<span class="card-stat mono" class:positive={hrs >= 0} class:negative={hrs < 0}>
								{hrs >= 0 ? '+' : ''}{hrs.toFixed(1)}h credits
							</span>
						{/if}
					</div>
					{#if storage}
						<div class="card-storage">
							<div class="storage-bar"><div class="storage-fill" style="width: {Math.min(100, storage.percent_used)}%"></div></div>
							<span class="storage-text mono">{storage.used_gb} / {storage.quota_gb} GB</span>
						</div>
					{/if}
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page { padding: var(--sp-5) var(--sp-6); display: flex; flex-direction: column; gap: var(--sp-4); max-width: 800px; }

	.page-header { display: flex; align-items: center; justify-content: space-between; }
	.page-title { font-family: var(--font-sans); font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }

	.create-bar { display: flex; gap: var(--sp-2); align-items: center; }
	.input {
		flex: 1; padding: 8px 12px; background: var(--surface-2); border: 1px solid var(--border);
		border-radius: 6px; color: var(--text-primary); font-size: 13px; outline: none;
	}
	.input:focus { border-color: var(--accent); }
	.input::placeholder { color: var(--text-tertiary); }
	.btn-primary {
		padding: 8px 16px; font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
		background: var(--accent); color: #000; border: none; border-radius: var(--radius-sm);
		cursor: pointer; transition: all 0.15s; white-space: nowrap;
	}
	.btn-primary:hover { background: #fff; }
	.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
	.error-text { font-size: 11px; color: var(--state-error); }

	.loading { text-align: center; padding: var(--sp-8); color: var(--text-tertiary); font-size: 12px; }
	.empty-state { display: flex; flex-direction: column; align-items: center; gap: var(--sp-2); padding: var(--sp-8); }
	.empty-text { font-size: 15px; color: var(--text-secondary); }
	.empty-hint { font-size: 11px; color: var(--text-tertiary); }

	.org-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--sp-3); }

	.org-card {
		background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md);
		padding: var(--sp-4); display: flex; flex-direction: column; gap: var(--sp-3);
		text-decoration: none; color: inherit; transition: all 0.15s; cursor: pointer;
	}
	.org-card:hover { border-color: var(--accent); background: var(--surface-3); }

	.card-top { display: flex; flex-direction: column; gap: var(--sp-1); }
	.org-name { font-size: 16px; font-weight: 600; color: var(--text-primary); }
	.card-badges { display: flex; gap: var(--sp-1); }
	.badge { font-size: 9px; letter-spacing: 0.06em; padding: 2px 6px; border-radius: 3px; }
	.badge.personal { background: rgba(255, 242, 3, 0.1); color: var(--accent); }
	.badge.team { background: rgba(0, 154, 218, 0.1); color: var(--secondary); }
	.badge.owner { background: rgba(255, 242, 3, 0.06); color: var(--text-tertiary); }

	.card-stats { display: flex; gap: var(--sp-3); }
	.card-stat { font-size: 11px; color: var(--text-tertiary); }
	.card-stat.positive { color: var(--state-complete); }
	.card-stat.negative { color: var(--state-error); }

	.card-storage { display: flex; flex-direction: column; gap: 4px; }
	.storage-bar { height: 4px; background: var(--surface-4); border-radius: 2px; overflow: hidden; }
	.storage-fill { height: 100%; background: var(--accent); border-radius: 2px; transition: width 0.3s; }
	.storage-text { font-size: 10px; color: var(--text-tertiary); }
</style>
