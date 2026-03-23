<script lang="ts">
	import { onMount } from 'svelte';
	import { getStoredUser } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { loadUserOrgs } from '$lib/stores/orgs';

	interface OrgInfo {
		org_id: string;
		name: string;
		owner_id: string;
		personal: boolean;
		created_at: number;
	}

	interface OrgMember {
		user_id: string;
		org_id: string;
		role: string;
		joined_at: number;
		email: string;
	}

	let orgs = $state<OrgInfo[]>([]);
	let loading = $state(true);
	let newOrgName = $state('');
	let creating = $state(false);
	let createError = $state('');

	// Detail view
	let selectedOrg = $state<OrgInfo | null>(null);
	let members = $state<OrgMember[]>([]);
	let membersLoading = $state(false);
	let orgCredits = $state<{ contributed_hours: number; consumed_hours: number; balance_seconds: number; ratio: number | null } | null>(null);
	let orgStorage = $state<{ used_gb: number; quota_gb: number; percent_used: number } | null>(null);
	let ipAllowlist = $state<string[]>([]);
	let newCidr = $state('');

	// Add member
	let addMemberEmail = $state('');
	let addMemberRole = $state('member');
	let addMemberError = $state('');

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
		} catch {
			orgs = [];
		}
	}

	async function createOrg() {
		if (!newOrgName.trim()) return;
		creating = true;
		createError = '';
		try {
			await authFetch('/api/orgs', {
				method: 'POST',
				body: JSON.stringify({ name: newOrgName.trim() })
			});
			newOrgName = '';
			await loadOrgs();
			loadUserOrgs(); // Update sidebar org switcher
		} catch (e) {
			createError = e instanceof Error ? e.message : 'Failed to create org';
		} finally {
			creating = false;
		}
	}

	async function selectOrg(org: OrgInfo) {
		selectedOrg = org;
		membersLoading = true;
		orgCredits = null;
		orgStorage = null;
		ipAllowlist = [];
		try {
			const [membersRes, creditsRes, storageRes] = await Promise.all([
				authFetch(`/api/orgs/${org.org_id}/members`),
				authFetch(`/api/orgs/${org.org_id}/credits`).catch(() => null),
				authFetch(`/api/orgs/${org.org_id}/storage`).catch(() => null),
			]);
			members = membersRes.members;
			orgCredits = creditsRes;
			orgStorage = storageRes;
			try {
				const alRes = await authFetch(`/api/orgs/${org.org_id}/ip-allowlist`);
				ipAllowlist = alRes.cidrs || [];
			} catch { ipAllowlist = []; }
		} catch {
			members = [];
		} finally {
			membersLoading = false;
		}
	}

	async function addMember() {
		if (!selectedOrg || !addMemberEmail.trim()) return;
		addMemberError = '';
		try {
			await authFetch(`/api/orgs/${selectedOrg.org_id}/members`, {
				method: 'POST',
				body: JSON.stringify({ email: addMemberEmail.trim(), role: addMemberRole })
			});
			addMemberEmail = '';
			await selectOrg(selectedOrg);
		} catch (e) {
			addMemberError = e instanceof Error ? e.message : 'Failed to add member';
		}
	}

	async function removeMember(memberId: string) {
		if (!selectedOrg) return;
		try {
			await authFetch(`/api/orgs/${selectedOrg.org_id}/members/${encodeURIComponent(memberId)}`, {
				method: 'DELETE'
			});
			await selectOrg(selectedOrg);
		} catch { /* ignore */ }
	}

	async function changeRole(memberId: string, role: string) {
		if (!selectedOrg) return;
		try {
			await authFetch(`/api/orgs/${selectedOrg.org_id}/members/${encodeURIComponent(memberId)}/role`, {
				method: 'PATCH',
				body: JSON.stringify({ role })
			});
			await selectOrg(selectedOrg);
		} catch { /* ignore */ }
	}

	async function deleteOrg(org: OrgInfo) {
		try {
			await authFetch(`/api/orgs/${org.org_id}`, { method: 'DELETE' });
			selectedOrg = null;
			await loadOrgs();
			loadUserOrgs(); // Update sidebar org switcher
		} catch { /* ignore */ }
	}

	async function addCidr() {
		if (!selectedOrg || !newCidr.trim()) return;
		const updated = [...ipAllowlist, newCidr.trim()];
		try {
			await authFetch(`/api/orgs/${selectedOrg.org_id}/ip-allowlist`, {
				method: 'PUT', body: JSON.stringify({ cidrs: updated })
			});
			ipAllowlist = updated;
			newCidr = '';
		} catch { /* ignore */ }
	}

	async function removeCidr(cidr: string) {
		if (!selectedOrg) return;
		const updated = ipAllowlist.filter(c => c !== cidr);
		try {
			await authFetch(`/api/orgs/${selectedOrg.org_id}/ip-allowlist`, {
				method: 'PUT', body: JSON.stringify({ cidrs: updated })
			});
			ipAllowlist = updated;
		} catch { /* ignore */ }
	}

	function isOwner(org: OrgInfo): boolean {
		return org.owner_id === userId;
	}

	function back() {
		selectedOrg = null;
	}

	onMount(async () => {
		await loadOrgs();
		// Auto-select org if navigated from profile page
		const preselected = localStorage.getItem('ck:selected_org');
		if (preselected) {
			localStorage.removeItem('ck:selected_org');
			const org = orgs.find(o => o.org_id === preselected);
			if (org) await selectOrg(org);
		}
		loading = false;
	});
</script>

<svelte:head>
	<title>Organizations — CorridorKey</title>
</svelte:head>

<div class="page">
	{#if loading}
		<div class="loading mono">Loading...</div>
	{:else if selectedOrg}
		<!-- Org detail view -->
		<div class="page-header">
			<button class="back-btn mono" onclick={back}>&larr; BACK</button>
			<h1 class="page-title">{selectedOrg.name}</h1>
			{#if selectedOrg.personal}
				<span class="org-badge mono personal">PERSONAL</span>
			{/if}
		</div>

		<div class="detail-layout">
			<!-- Credits & Storage -->
			{#if orgCredits || orgStorage}
				<div class="stats-row">
					{#if orgCredits}
						<section class="stat-card">
							<h2 class="card-title mono">GPU CREDITS</h2>
							<div class="credit-bars">
								<div class="credit-row">
									<span class="credit-label mono">CONTRIBUTED</span>
									<span class="credit-value mono">{orgCredits.contributed_hours}h</span>
								</div>
								<div class="credit-row">
									<span class="credit-label mono">CONSUMED</span>
									<span class="credit-value mono">{orgCredits.consumed_hours}h</span>
								</div>
								<div class="credit-balance" class:positive={orgCredits.balance_seconds >= 0} class:negative={orgCredits.balance_seconds < 0}>
									<span class="balance-label mono">BALANCE</span>
									<span class="balance-value mono">{orgCredits.balance_seconds >= 0 ? '+' : ''}{(orgCredits.balance_seconds / 3600).toFixed(2)}h</span>
								</div>
							</div>
						</section>
					{/if}
					{#if orgStorage}
						<section class="stat-card">
							<h2 class="card-title mono">STORAGE</h2>
							<div class="storage-info">
								<div class="storage-bar">
									<div class="storage-fill" style="width: {Math.min(100, orgStorage.percent_used)}%"></div>
								</div>
								<span class="storage-text mono">{orgStorage.used_gb} GB / {orgStorage.quota_gb} GB ({orgStorage.percent_used}%)</span>
							</div>
						</section>
					{/if}
				</div>
			{/if}

			<!-- Members -->
			<section class="detail-card">
				<h2 class="card-title mono">MEMBERS</h2>
				{#if membersLoading}
					<p class="card-desc">Loading...</p>
				{:else}
					<div class="member-list">
						{#each members as m (m.user_id)}
							<div class="member-row">
								<span class="member-id">{m.email || m.user_id.substring(0, 20) + '...'}</span>
								<span class="role-badge mono" data-role={m.role}>{m.role.toUpperCase()}</span>
								{#if isOwner(selectedOrg) && m.role !== 'owner'}
									<select
										class="role-select mono"
										value={m.role}
										onchange={(e) => changeRole(m.user_id, (e.target as HTMLSelectElement).value)}
									>
										<option value="member">member</option>
										<option value="admin">admin</option>
									</select>
									<button class="btn-icon" onclick={() => removeMember(m.user_id)} title="Remove">
										<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.5"/></svg>
									</button>
								{/if}
							</div>
						{/each}
					</div>

					{#if isOwner(selectedOrg)}
						<div class="add-member">
							<h3 class="sub-title mono">ADD MEMBER</h3>
							{#if addMemberError}
								<div class="form-error mono">{addMemberError}</div>
							{/if}
							<div class="add-member-row">
								<input
									type="email"
									class="input"
									bind:value={addMemberEmail}
									placeholder="user@email.com"
								/>
								<select class="role-select mono" bind:value={addMemberRole}>
									<option value="member">member</option>
									<option value="admin">admin</option>
								</select>
								<button class="btn btn-primary mono" onclick={addMember}>ADD</button>
							</div>
						</div>
					{/if}
				{/if}
			</section>

			<!-- IP Allowlist (org admins only) -->
			{#if isOwner(selectedOrg)}
				<section class="detail-card">
					<h2 class="card-title mono">IP ALLOWLIST</h2>
					{#if ipAllowlist.length === 0}
						<p class="card-desc">No IP restrictions. All IPs can access this org.</p>
					{:else}
						<div class="cidr-list">
							{#each ipAllowlist as cidr}
								<div class="cidr-row">
									<span class="mono">{cidr}</span>
									<button class="btn-icon" onclick={() => removeCidr(cidr)} title="Remove">
										<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.5"/></svg>
									</button>
								</div>
							{/each}
						</div>
					{/if}
					<div class="add-cidr-row">
						<input type="text" class="input mono" bind:value={newCidr} placeholder="192.168.1.0/24" />
						<button class="btn btn-primary mono" onclick={addCidr}>ADD</button>
					</div>
				</section>
			{/if}

			{#if isOwner(selectedOrg) && !selectedOrg.personal}
				<button class="btn btn-danger mono" onclick={() => deleteOrg(selectedOrg)}>
					DELETE ORGANIZATION
				</button>
			{/if}
		</div>
	{:else}
		<!-- Org list view -->
		<div class="page-header">
			<h1 class="page-title">Organizations</h1>
		</div>

		<div class="list-layout">
			<!-- Create -->
			<section class="detail-card">
				<h2 class="card-title mono">CREATE ORGANIZATION</h2>
				{#if createError}
					<div class="form-error mono">{createError}</div>
				{/if}
				<div class="create-row">
					<input
						type="text"
						class="input"
						bind:value={newOrgName}
						placeholder="Organization name"
					/>
					<button class="btn btn-primary mono" onclick={createOrg} disabled={creating}>
						{creating ? 'Creating...' : 'Create'}
					</button>
				</div>
			</section>

			<!-- List -->
			<section class="detail-card">
				<h2 class="card-title mono">YOUR ORGANIZATIONS <span class="count">{orgs.length}</span></h2>
				{#if orgs.length === 0}
					<p class="card-desc">No organizations yet.</p>
				{:else}
					<div class="org-list">
						{#each orgs as org (org.org_id)}
							<button class="org-row" onclick={() => selectOrg(org)}>
								<span class="org-name">{org.name}</span>
								{#if org.personal}
									<span class="org-badge mono personal">PERSONAL</span>
								{:else}
									<span class="org-badge mono team">TEAM</span>
								{/if}
								{#if isOwner(org)}
									<span class="owner-badge mono">OWNER</span>
								{/if}
								<svg class="chevron" width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5"/></svg>
							</button>
						{/each}
					</div>
				{/if}
			</section>
		</div>
	{/if}
</div>

<style>
	.page {
		padding: var(--sp-5) var(--sp-6);
		max-width: 640px;
		height: 100%;
		overflow-y: auto;
	}

	.loading { display: flex; align-items: center; justify-content: center; height: 40vh; color: var(--text-tertiary); }

	.page-header {
		display: flex; align-items: center; gap: var(--sp-3);
		margin-bottom: var(--sp-5); padding-bottom: var(--sp-3);
		border-bottom: 1px solid var(--border);
	}
	.page-title { font-size: 20px; font-weight: 700; }

	.back-btn {
		font-size: 11px; letter-spacing: 0.06em; color: var(--text-tertiary);
		background: none; border: 1px solid var(--border); border-radius: var(--radius-sm);
		padding: 4px 10px; cursor: pointer;
	}
	.back-btn:hover { color: var(--text-primary); border-color: var(--text-tertiary); }

	.list-layout, .detail-layout { display: flex; flex-direction: column; gap: var(--sp-4); }

	.detail-card {
		display: flex; flex-direction: column; gap: var(--sp-3);
		padding: var(--sp-4); background: var(--surface-2);
		border: 1px solid var(--border); border-radius: var(--radius-lg);
	}
	.card-title { font-size: 10px; font-weight: 600; letter-spacing: 0.12em; color: var(--accent); display: flex; align-items: center; gap: var(--sp-2); }
	.card-desc { font-size: 13px; color: var(--text-secondary); }
	.count { font-size: 9px; background: var(--surface-4); padding: 1px 6px; border-radius: 8px; color: var(--text-secondary); }
	.sub-title { font-size: 10px; letter-spacing: 0.1em; color: var(--text-tertiary); margin-top: var(--sp-2); }

	.org-list { display: flex; flex-direction: column; gap: 1px; border-radius: var(--radius-md); overflow: hidden; }
	.org-row {
		display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-3) var(--sp-4);
		background: var(--surface-3); border: none; cursor: pointer; text-align: left;
		color: var(--text-primary); font-size: 14px; width: 100%; transition: background 0.1s;
	}
	.org-row:hover { background: var(--surface-4); }
	.org-name { flex: 1; }
	.chevron { color: var(--text-tertiary); flex-shrink: 0; }

	.org-badge { font-size: 10px; letter-spacing: 0.06em; padding: 2px 8px; border-radius: 3px; }
	.org-badge.personal { background: var(--accent-muted); color: var(--accent-dim); }
	.org-badge.team { background: var(--secondary-muted); color: var(--secondary); }
	.owner-badge { font-size: 9px; letter-spacing: 0.06em; color: var(--accent); opacity: 0.6; }

	.member-list { display: flex; flex-direction: column; gap: var(--sp-2); }
	.member-row { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2) 0; }
	.member-id { flex: 1; font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; }

	.role-badge { font-size: 10px; letter-spacing: 0.06em; padding: 2px 8px; border-radius: 3px; font-weight: 600; }
	.role-badge[data-role="owner"] { background: rgba(255, 242, 3, 0.12); color: var(--accent); }
	.role-badge[data-role="admin"] { background: rgba(206, 147, 216, 0.12); color: var(--state-masked); }
	.role-badge[data-role="member"] { background: rgba(93, 216, 121, 0.12); color: var(--state-complete); }

	.role-select {
		font-size: 11px; padding: 3px 6px; background: var(--surface-3);
		border: 1px solid var(--border); border-radius: var(--radius-sm);
		color: var(--text-secondary); cursor: pointer; outline: none;
	}
	.role-select:focus { border-color: var(--accent); }

	.btn-icon {
		background: none; border: none; cursor: pointer; color: var(--text-tertiary);
		padding: 2px; border-radius: 3px; display: flex; align-items: center;
	}
	.btn-icon:hover { color: var(--state-error); }

	.create-row, .add-member-row { display: flex; gap: var(--sp-2); align-items: center; }
	.input {
		flex: 1; padding: 8px 12px; background: var(--surface-3);
		border: 1px solid var(--border); border-radius: var(--radius-sm);
		color: var(--text-primary); font-size: 14px; outline: none; font-family: inherit;
	}
	.input:focus { border-color: var(--accent); }
	.input::placeholder { color: var(--text-tertiary); }

	.btn { font-size: 11px; letter-spacing: 0.06em; padding: 8px 14px; border: none; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.15s; flex-shrink: 0; }
	.btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.btn-primary { background: var(--accent); color: #000; font-weight: 600; }
	.btn-primary:hover:not(:disabled) { background: #fff; }
	.btn-danger { background: transparent; border: 1px solid rgba(255, 82, 82, 0.3); color: var(--state-error); align-self: flex-start; }
	.btn-danger:hover { background: rgba(255, 82, 82, 0.1); }

	.form-error { padding: var(--sp-2) var(--sp-3); background: rgba(255, 82, 82, 0.08); border: 1px solid rgba(255, 82, 82, 0.2); border-radius: 6px; font-size: 12px; color: var(--state-error); }

	.stats-row { display: flex; gap: var(--sp-3); }
	.stat-card {
		flex: 1; display: flex; flex-direction: column; gap: var(--sp-3);
		padding: var(--sp-4); background: var(--surface-2);
		border: 1px solid var(--border); border-radius: var(--radius-lg);
	}
	.credit-bars { display: flex; flex-direction: column; gap: var(--sp-2); }
	.credit-row { display: flex; justify-content: space-between; align-items: center; }
	.credit-label { font-size: 10px; letter-spacing: 0.08em; color: var(--text-tertiary); }
	.credit-value { font-size: 14px; font-weight: 600; color: var(--text-primary); }
	.credit-balance {
		display: flex; justify-content: space-between; align-items: center;
		padding-top: var(--sp-2); border-top: 1px solid var(--border); margin-top: var(--sp-1);
	}
	.balance-label { font-size: 10px; letter-spacing: 0.08em; color: var(--text-tertiary); }
	.balance-value { font-size: 16px; font-weight: 700; }
	.credit-balance.positive .balance-value { color: var(--state-complete); }
	.credit-balance.negative .balance-value { color: var(--state-error); }

	.storage-info { display: flex; flex-direction: column; gap: var(--sp-2); }
	.storage-bar {
		height: 6px; background: var(--surface-4); border-radius: 3px; overflow: hidden;
	}
	.storage-fill {
		height: 100%; background: var(--accent); border-radius: 3px;
		transition: width 0.3s;
	}
	.storage-text { font-size: 12px; color: var(--text-secondary); }

	.cidr-list { display: flex; flex-direction: column; gap: var(--sp-1); }
	.cidr-row { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-1) 0; }
	.add-cidr-row { display: flex; gap: var(--sp-2); margin-top: var(--sp-2); }

	.add-member { border-top: 1px solid var(--border); padding-top: var(--sp-3); display: flex; flex-direction: column; gap: var(--sp-2); }
</style>
