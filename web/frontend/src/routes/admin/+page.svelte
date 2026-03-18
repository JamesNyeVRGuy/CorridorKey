<script lang="ts">
	import { onMount } from 'svelte';
	import { getStoredUser } from '$lib/auth';

	interface UserRecord {
		user_id: string;
		email: string;
		tier: string;
		name: string;
		signed_up_at: number;
		approved_at: number;
		approved_by: string;
	}

	interface OrgRecord {
		org_id: string;
		name: string;
		owner_id: string;
		personal: boolean;
		created_at: number;
		member_count: number;
	}

	const TIERS = ['pending', 'member', 'contributor', 'org_admin', 'platform_admin'];

	let authorized = $state(false);
	let activeTab = $state<'users' | 'orgs'>('users');
	let users = $state<UserRecord[]>([]);
	let pendingUsers = $state<UserRecord[]>([]);
	let orgs = $state<OrgRecord[]>([]);
	let loading = $state(true);
	let actionInProgress = $state<string | null>(null);
	let inviteUrl = $state('');
	let inviteGenerating = $state(false);
	let invites = $state<{ token: string; created_at: number; used: boolean; used_by: string | null }[]>([]);

	async function adminFetch(path: string, opts?: RequestInit) {
		const token = localStorage.getItem('ck:auth_token');
		const headers: Record<string, string> = { 'Content-Type': 'application/json' };
		if (token) headers['Authorization'] = `Bearer ${token}`;
		const res = await fetch(path, { ...opts, headers });
		if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
		return res.json();
	}

	async function loadUsers() {
		const [allRes, pendingRes] = await Promise.all([
			adminFetch('/api/admin/users'),
			adminFetch('/api/admin/users/pending')
		]);
		users = allRes.users;
		pendingUsers = pendingRes.users;
	}

	let inviteError = $state('');

	async function generateInvite() {
		inviteGenerating = true;
		inviteUrl = '';
		inviteError = '';
		try {
			const res = await adminFetch('/api/auth/invite/generate', { method: 'POST' });
			inviteUrl = `${window.location.origin}${res.signup_url}`;
			await loadInvites();
		} catch (e) {
			inviteError = e instanceof Error ? e.message : 'Failed to generate invite';
		} finally {
			inviteGenerating = false;
		}
	}

	async function copyInvite() {
		await navigator.clipboard.writeText(inviteUrl);
	}

	async function loadInvites() {
		try {
			const res = await adminFetch('/api/auth/invites');
			invites = res.invites;
		} catch {
			invites = [];
		}
	}

	async function loadOrgs() {
		const res = await adminFetch('/api/admin/orgs');
		orgs = res.orgs;
	}

	async function approveUser(userId: string) {
		actionInProgress = userId;
		try {
			await adminFetch(`/api/admin/users/${encodeURIComponent(userId)}/approve`, { method: 'POST' });
			await loadUsers();
		} finally {
			actionInProgress = null;
		}
	}

	async function rejectUser(userId: string) {
		actionInProgress = userId;
		try {
			await adminFetch(`/api/admin/users/${encodeURIComponent(userId)}/reject`, { method: 'POST' });
			await loadUsers();
		} finally {
			actionInProgress = null;
		}
	}

	async function setTier(userId: string, tier: string) {
		actionInProgress = userId;
		try {
			await adminFetch(`/api/admin/users/${encodeURIComponent(userId)}/tier`, {
				method: 'POST',
				body: JSON.stringify({ tier })
			});
			await loadUsers();
		} finally {
			actionInProgress = null;
		}
	}

	function formatDate(ts: number): string {
		if (!ts) return '—';
		return new Date(ts * 1000).toLocaleDateString('en-US', {
			month: 'short', day: 'numeric', year: 'numeric'
		});
	}

	onMount(async () => {
		const user = getStoredUser();
		if (user?.tier !== 'platform_admin') {
			authorized = false;
			loading = false;
			return;
		}
		authorized = true;
		try {
			await Promise.all([loadUsers(), loadOrgs(), loadInvites()]);
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head>
	<title>Admin — CorridorKey</title>
</svelte:head>

<div class="admin-page">
	{#if !authorized && !loading}
		<div class="denied">
			<span class="denied-icon">ACCESS DENIED</span>
			<p>This page requires platform_admin privileges.</p>
		</div>
	{:else if loading}
		<div class="loading mono">Loading...</div>
	{:else}
		<div class="admin-header">
			<h1 class="page-title mono">ADMIN</h1>
			<div class="tab-bar">
				<button
					class="tab-btn mono"
					class:active={activeTab === 'users'}
					onclick={() => activeTab = 'users'}
				>
					USERS
					{#if pendingUsers.length > 0}
						<span class="tab-badge">{pendingUsers.length}</span>
					{/if}
				</button>
				<button
					class="tab-btn mono"
					class:active={activeTab === 'orgs'}
					onclick={() => activeTab = 'orgs'}
				>ORGS</button>
			</div>
		</div>

		{#if activeTab === 'users'}
			<!-- Invite Generation -->
			<div class="section">
				<h2 class="section-title mono">INVITE LINK</h2>
				<div class="invite-row">
					<button class="btn btn-primary mono" onclick={generateInvite} disabled={inviteGenerating}>
						{inviteGenerating ? 'Generating...' : 'Generate Invite Link'}
					</button>
					{#if inviteError}
						<div class="form-error mono">{inviteError}</div>
					{/if}
					{#if inviteUrl}
						<div class="invite-result">
							<input type="text" class="invite-url mono" value={inviteUrl} readonly />
							<button class="btn btn-copy mono" onclick={copyInvite}>COPY</button>
						</div>
					{/if}
				</div>
				{#if invites.length > 0}
					<div class="invite-list">
						<table class="data-table">
							<thead>
								<tr>
									<th class="mono">TOKEN</th>
									<th class="mono">STATUS</th>
									<th class="mono">USED BY</th>
									<th class="mono">CREATED</th>
								</tr>
							</thead>
							<tbody>
								{#each invites as inv}
									<tr>
										<td class="mono">{inv.token}</td>
										<td>
											{#if inv.used}
												<span class="status-badge used mono">USED</span>
											{:else}
												<span class="status-badge available mono">AVAILABLE</span>
											{/if}
										</td>
										<td class="mono">{inv.used_by ?? '—'}</td>
										<td class="mono">{formatDate(inv.created_at)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<!-- Pending Approvals -->
			{#if pendingUsers.length > 0}
				<div class="section">
					<h2 class="section-title mono">PENDING APPROVAL</h2>
					<div class="pending-list">
						{#each pendingUsers as pu (pu.user_id)}
							<div class="pending-card">
								<div class="pending-info">
									<span class="pending-email">{pu.email}</span>
									{#if pu.name}
										<span class="pending-name mono">{pu.name}</span>
									{/if}
									<span class="pending-date mono">{formatDate(pu.signed_up_at)}</span>
								</div>
								<div class="pending-actions">
									<button
										class="btn btn-approve mono"
										onclick={() => approveUser(pu.user_id)}
										disabled={actionInProgress === pu.user_id}
									>APPROVE</button>
									<button
										class="btn btn-reject mono"
										onclick={() => rejectUser(pu.user_id)}
										disabled={actionInProgress === pu.user_id}
									>REJECT</button>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- All Users -->
			<div class="section">
				<h2 class="section-title mono">ALL USERS <span class="count">{users.length}</span></h2>
				<div class="table-wrap">
					<table class="data-table">
						<thead>
							<tr>
								<th class="mono">EMAIL</th>
								<th class="mono">TIER</th>
								<th class="mono">SIGNED UP</th>
								<th class="mono">ACTIONS</th>
							</tr>
						</thead>
						<tbody>
							{#each users as u (u.user_id)}
								<tr>
									<td>
										<span class="user-email">{u.email}</span>
										{#if u.name}<span class="user-name mono">{u.name}</span>{/if}
									</td>
									<td>
										<span class="tier-badge mono" data-tier={u.tier}>{u.tier}</span>
									</td>
									<td class="mono">{formatDate(u.signed_up_at)}</td>
									<td>
										<select
											class="tier-select mono"
											value={u.tier}
											onchange={(e) => setTier(u.user_id, (e.target as HTMLSelectElement).value)}
											disabled={actionInProgress === u.user_id}
										>
											{#each TIERS as t}
												<option value={t}>{t}</option>
											{/each}
										</select>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{:else}
			<!-- Organizations -->
			<div class="section">
				<h2 class="section-title mono">ALL ORGANIZATIONS <span class="count">{orgs.length}</span></h2>
				<div class="table-wrap">
					<table class="data-table">
						<thead>
							<tr>
								<th class="mono">NAME</th>
								<th class="mono">OWNER</th>
								<th class="mono">MEMBERS</th>
								<th class="mono">TYPE</th>
								<th class="mono">CREATED</th>
							</tr>
						</thead>
						<tbody>
							{#each orgs as org (org.org_id)}
								<tr>
									<td>{org.name}</td>
									<td class="mono">{org.owner_id.substring(0, 12)}...</td>
									<td class="mono">{org.member_count}</td>
									<td>
										{#if org.personal}
											<span class="org-type mono personal">PERSONAL</span>
										{:else}
											<span class="org-type mono team">TEAM</span>
										{/if}
									</td>
									<td class="mono">{formatDate(org.created_at)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}
	{/if}
</div>

<style>
	.admin-page {
		padding: var(--sp-6);
		max-width: 960px;
		height: 100%;
		overflow-y: auto;
	}

	.denied {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 60vh;
		gap: var(--sp-3);
		color: var(--text-tertiary);
	}

	.denied-icon {
		font-family: var(--font-mono);
		font-size: 14px;
		letter-spacing: 0.2em;
		color: var(--state-error);
		padding: var(--sp-2) var(--sp-4);
		border: 1px solid var(--state-error);
		border-radius: var(--radius-sm);
	}

	.loading {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 40vh;
		color: var(--text-tertiary);
	}

	.admin-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: var(--sp-6);
		padding-bottom: var(--sp-4);
		border-bottom: 1px solid var(--border);
	}

	.page-title {
		font-size: 11px;
		letter-spacing: 0.2em;
		color: var(--text-tertiary);
		font-weight: 500;
	}

	.tab-bar {
		display: flex;
		gap: 2px;
		background: var(--surface-2);
		border-radius: var(--radius-sm);
		padding: 2px;
	}

	.tab-btn {
		font-size: 11px;
		letter-spacing: 0.08em;
		padding: 6px 14px;
		border: none;
		background: transparent;
		color: var(--text-tertiary);
		border-radius: 3px;
		cursor: pointer;
		transition: all 0.15s;
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.tab-btn:hover { color: var(--text-secondary); }
	.tab-btn.active {
		background: var(--surface-4);
		color: var(--accent);
	}

	.tab-badge {
		min-width: 16px;
		height: 14px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0 4px;
		font-size: 9px;
		font-weight: 700;
		background: var(--state-error);
		color: #000;
		border-radius: 7px;
	}

	.section {
		margin-bottom: var(--sp-6);
	}

	.section-title {
		font-size: 10px;
		letter-spacing: 0.15em;
		color: var(--text-tertiary);
		margin-bottom: var(--sp-3);
		display: flex;
		align-items: center;
		gap: var(--sp-2);
	}

	.count {
		font-size: 9px;
		background: var(--surface-4);
		padding: 1px 6px;
		border-radius: 8px;
		color: var(--text-secondary);
	}

	/* Pending cards */
	.pending-list {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.pending-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--sp-3) var(--sp-4);
		background: var(--surface-1);
		border: 1px solid rgba(255, 242, 3, 0.12);
		border-radius: var(--radius-md);
	}

	.pending-info {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
	}

	.pending-email {
		font-size: 14px;
		color: var(--text-primary);
	}

	.pending-name {
		font-size: 11px;
		color: var(--text-tertiary);
	}

	.pending-date {
		font-size: 11px;
		color: var(--text-tertiary);
	}

	.pending-actions {
		display: flex;
		gap: var(--sp-2);
	}

	.btn {
		font-size: 11px;
		letter-spacing: 0.06em;
		padding: 5px 12px;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all 0.15s;
		background: transparent;
	}

	.btn:disabled { opacity: 0.4; cursor: not-allowed; }

	.btn-approve {
		color: var(--state-complete);
		border-color: rgba(93, 216, 121, 0.3);
	}
	.btn-approve:hover:not(:disabled) {
		background: rgba(93, 216, 121, 0.1);
	}

	.btn-reject {
		color: var(--state-error);
		border-color: rgba(255, 82, 82, 0.3);
	}
	.btn-reject:hover:not(:disabled) {
		background: rgba(255, 82, 82, 0.1);
	}

	.btn-primary {
		background: var(--accent);
		color: #000;
		font-weight: 600;
	}
	.btn-primary:hover:not(:disabled) { background: #fff; }

	.btn-copy {
		color: var(--accent);
		border-color: var(--accent-dim);
	}
	.btn-copy:hover:not(:disabled) { background: var(--accent-muted); }

	.invite-row {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
	}

	.invite-result {
		display: flex;
		gap: var(--sp-2);
		align-items: center;
	}

	.invite-url {
		flex: 1;
		padding: 8px 12px;
		background: var(--surface-3);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		font-size: 12px;
		outline: none;
	}
	.invite-url:focus { border-color: var(--accent); }

	.invite-list {
		margin-top: var(--sp-3);
	}

	.status-badge {
		font-size: 10px;
		letter-spacing: 0.06em;
		padding: 2px 8px;
		border-radius: 3px;
		font-weight: 600;
	}
	.status-badge.available {
		background: rgba(93, 216, 121, 0.12);
		color: var(--state-complete);
	}
	.status-badge.used {
		background: rgba(117, 117, 117, 0.12);
		color: var(--state-cancelled);
	}

	.form-error {
		padding: var(--sp-2) var(--sp-3);
		background: rgba(255, 82, 82, 0.08);
		border: 1px solid rgba(255, 82, 82, 0.2);
		border-radius: 6px;
		font-size: 12px;
		color: var(--state-error);
	}

	/* Data table */
	.table-wrap {
		overflow-x: auto;
	}

	.data-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 13px;
	}

	.data-table th {
		font-size: 10px;
		letter-spacing: 0.1em;
		color: var(--text-tertiary);
		text-align: left;
		padding: var(--sp-2) var(--sp-3);
		border-bottom: 1px solid var(--border);
		font-weight: 500;
	}

	.data-table td {
		padding: var(--sp-2) var(--sp-3);
		border-bottom: 1px solid var(--border-subtle);
		color: var(--text-secondary);
		vertical-align: middle;
	}

	.data-table tr:hover td {
		background: var(--surface-1);
	}

	.user-email {
		color: var(--text-primary);
		display: block;
	}

	.user-name {
		font-size: 11px;
		color: var(--text-tertiary);
	}

	/* Tier badges */
	.tier-badge {
		font-size: 10px;
		letter-spacing: 0.06em;
		padding: 2px 8px;
		border-radius: 3px;
		font-weight: 600;
	}

	.tier-badge[data-tier="pending"] {
		background: rgba(255, 242, 3, 0.12);
		color: var(--accent);
	}
	.tier-badge[data-tier="member"] {
		background: rgba(93, 216, 121, 0.12);
		color: var(--state-complete);
	}
	.tier-badge[data-tier="contributor"] {
		background: rgba(0, 154, 218, 0.12);
		color: var(--secondary);
	}
	.tier-badge[data-tier="org_admin"] {
		background: rgba(206, 147, 216, 0.12);
		color: var(--state-masked);
	}
	.tier-badge[data-tier="platform_admin"] {
		background: rgba(255, 82, 82, 0.12);
		color: var(--state-error);
	}
	.tier-badge[data-tier="rejected"] {
		background: rgba(117, 117, 117, 0.12);
		color: var(--state-cancelled);
	}

	.tier-select {
		font-size: 11px;
		padding: 4px 8px;
		background: var(--surface-3);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-secondary);
		cursor: pointer;
		outline: none;
	}

	.tier-select:focus {
		border-color: var(--accent);
	}

	/* Org type badges */
	.org-type {
		font-size: 10px;
		letter-spacing: 0.06em;
		padding: 2px 8px;
		border-radius: 3px;
	}

	.org-type.personal {
		background: var(--accent-muted);
		color: var(--accent-dim);
	}

	.org-type.team {
		background: var(--secondary-muted);
		color: var(--secondary);
	}
</style>
