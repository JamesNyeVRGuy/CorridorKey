<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getStoredUser } from '$lib/auth';
	import { goto } from '$app/navigation';
	import { loadUserOrgs } from '$lib/stores/orgs';

	const orgId = $derived(page.params.id);
	const userId = getStoredUser()?.id ?? '';

	let org = $state<{ org_id: string; name: string; owner_id: string; personal: boolean } | null>(null);
	let members = $state<{ user_id: string; org_id: string; role: string; joined_at: number; email: string }[]>([]);
	let credits = $state<{ contributed_hours: number; consumed_hours: number; balance_seconds: number } | null>(null);
	let storage = $state<{ used_gb: number; quota_gb: number; percent_used: number } | null>(null);
	let ipAllowlist = $state<string[]>([]);
	let preferences = $state<{ allow_shared_nodes: boolean }>({ allow_shared_nodes: true });
	let webhooks = $state<{ id: string; url: string; events: string[]; format: string }[]>([]);
	let loading = $state(true);

	// Forms
	let addEmail = $state('');
	let addRole = $state('member');
	let addError = $state('');
	let newCidr = $state('');
	let newWebhookUrl = $state('');
	let newWebhookEvents = $state<Set<string>>(new Set(['job_completed', 'job_failed']));
	let newWebhookFormat = $state('json');

	async function authFetch(path: string, opts?: RequestInit) {
		const token = localStorage.getItem('ck:auth_token');
		const headers: Record<string, string> = { 'Content-Type': 'application/json' };
		if (token) headers['Authorization'] = `Bearer ${token}`;
		const res = await fetch(path, { ...opts, headers });
		if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
		return res.json();
	}

	async function loadAll() {
		const [orgRes, membersRes, creditsRes, storageRes, alRes, prefsRes, hooksRes] = await Promise.all([
			authFetch(`/api/orgs/${orgId}`),
			authFetch(`/api/orgs/${orgId}/members`),
			authFetch(`/api/orgs/${orgId}/credits`).catch(() => null),
			authFetch(`/api/orgs/${orgId}/storage`).catch(() => null),
			authFetch(`/api/orgs/${orgId}/ip-allowlist`).catch(() => ({ cidrs: [] })),
			authFetch(`/api/orgs/${orgId}/preferences`).catch(() => ({ allow_shared_nodes: true })),
			authFetch(`/api/orgs/${orgId}/webhooks`).catch(() => ({ webhooks: [] })),
		]);
		org = orgRes;
		members = membersRes.members;
		credits = creditsRes;
		storage = storageRes;
		ipAllowlist = alRes.cidrs || [];
		preferences = prefsRes;
		webhooks = hooksRes.webhooks || [];
	}

	function isOwner(): boolean { return org?.owner_id === userId; }

	async function addMember() {
		if (!addEmail.trim()) return;
		addError = '';
		try {
			await authFetch(`/api/orgs/${orgId}/members`, { method: 'POST', body: JSON.stringify({ email: addEmail.trim(), role: addRole }) });
			addEmail = ''; await loadAll();
		} catch (e) { addError = e instanceof Error ? e.message : 'Failed'; }
	}

	async function removeMember(uid: string) {
		await authFetch(`/api/orgs/${orgId}/members/${encodeURIComponent(uid)}`, { method: 'DELETE' });
		await loadAll();
	}

	async function changeRole(uid: string, role: string) {
		await authFetch(`/api/orgs/${orgId}/members/${encodeURIComponent(uid)}/role`, { method: 'PATCH', body: JSON.stringify({ role }) });
		await loadAll();
	}

	async function savePreferences() {
		await authFetch(`/api/orgs/${orgId}/preferences`, { method: 'PUT', body: JSON.stringify(preferences) });
	}

	async function addCidr() {
		if (!newCidr.trim()) return;
		const updated = [...ipAllowlist, newCidr.trim()];
		await authFetch(`/api/orgs/${orgId}/ip-allowlist`, { method: 'PUT', body: JSON.stringify({ cidrs: updated }) });
		ipAllowlist = updated; newCidr = '';
	}

	async function removeCidr(cidr: string) {
		const updated = ipAllowlist.filter(c => c !== cidr);
		await authFetch(`/api/orgs/${orgId}/ip-allowlist`, { method: 'PUT', body: JSON.stringify({ cidrs: updated }) });
		ipAllowlist = updated;
	}

	async function addWebhook() {
		if (!newWebhookUrl.trim()) return;
		await authFetch(`/api/orgs/${orgId}/webhooks`, {
			method: 'POST', body: JSON.stringify({ url: newWebhookUrl.trim(), events: [...newWebhookEvents], format: newWebhookFormat }),
		});
		newWebhookUrl = ''; await loadAll();
	}

	async function deleteWebhook(hookId: string) {
		await authFetch(`/api/orgs/${orgId}/webhooks/${hookId}`, { method: 'DELETE' });
		await loadAll();
	}

	function toggleWebhookEvent(event: string) {
		const next = new Set(newWebhookEvents);
		if (next.has(event)) next.delete(event); else next.add(event);
		newWebhookEvents = next;
	}

	async function deleteOrg() {
		if (!confirm(`Delete "${org?.name}" and all data? This cannot be undone.`)) return;
		await authFetch(`/api/orgs/${orgId}`, { method: 'DELETE' });
		loadUserOrgs();
		goto('/orgs');
	}

	onMount(async () => {
		try { await loadAll(); } catch { /* ignore */ }
		finally { loading = false; }
	});
</script>

<svelte:head>
	<title>{org?.name ?? 'Org'} — CorridorKey</title>
</svelte:head>

<div class="page">
	{#if loading}
		<div class="loading mono">Loading...</div>
	{:else if org}
		<div class="page-header">
			<a href="/orgs" class="back-link mono">&larr; Organizations</a>
			<div class="title-row">
				<h1 class="page-title">{org.name}</h1>
				{#if org.personal}<span class="badge personal mono">PERSONAL</span>{/if}
				{#if !org.personal}<span class="badge team mono">TEAM</span>{/if}
			</div>
		</div>

		<!-- Stats cards -->
		<div class="stats-grid">
			{#if credits}
				<div class="stat-card">
					<span class="stat-label mono">CREDIT BALANCE</span>
					<span class="stat-value mono" class:positive={credits.balance_seconds >= 0} class:negative={credits.balance_seconds < 0}>
						{(credits.balance_seconds / 3600).toFixed(1)}h
					</span>
					<span class="stat-detail mono">{credits.contributed_hours}h in · {credits.consumed_hours}h out</span>
				</div>
			{/if}
			{#if storage}
				<div class="stat-card">
					<span class="stat-label mono">STORAGE</span>
					<div class="storage-bar"><div class="storage-fill" style="width: {Math.min(100, storage.percent_used)}%"></div></div>
					<span class="stat-detail mono">{storage.used_gb} / {storage.quota_gb} GB ({storage.percent_used}%)</span>
				</div>
			{/if}
			<div class="stat-card">
				<span class="stat-label mono">MEMBERS</span>
				<span class="stat-value mono">{members.length}</span>
			</div>
		</div>

		<!-- Members -->
		<section class="section-card">
			<h2 class="section-title mono">MEMBERS</h2>
			<div class="member-list">
				{#each members as m (m.user_id)}
					<div class="member-row">
						<span class="member-email">{m.email || m.user_id.substring(0, 16) + '...'}</span>
						<span class="role-badge mono" data-role={m.role}>{m.role}</span>
						{#if isOwner() && m.role !== 'owner'}
							<select class="select-sm mono" value={m.role} onchange={(e) => changeRole(m.user_id, (e.target as HTMLSelectElement).value)}>
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
			{#if isOwner()}
				{#if addError}<div class="form-error mono">{addError}</div>{/if}
				<div class="form-row">
					<input type="email" class="input mono" bind:value={addEmail} placeholder="user@email.com" />
					<select class="select-sm mono" bind:value={addRole}><option value="member">member</option><option value="admin">admin</option></select>
					<button class="btn-primary mono" onclick={addMember}>ADD</button>
				</div>
			{/if}
		</section>

		<!-- Preferences -->
		<section class="section-card">
			<h2 class="section-title mono">PREFERENCES</h2>
			<label class="toggle-row">
				<input type="checkbox" bind:checked={preferences.allow_shared_nodes} onchange={savePreferences} class="toggle" />
				<div class="toggle-info">
					<span>Allow shared community nodes</span>
					<span class="toggle-hint mono">When disabled, only your org's private nodes process jobs.</span>
				</div>
			</label>
		</section>

		<!-- Webhooks -->
		{#if isOwner()}
			<section class="section-card">
				<h2 class="section-title mono">WEBHOOKS</h2>
				{#if webhooks.length > 0}
					<div class="webhook-list">
						{#each webhooks as hook}
							<div class="webhook-row">
								<span class="webhook-url mono">{hook.url}</span>
								<span class="webhook-events mono">{hook.events.join(', ')}</span>
								<button class="btn-icon" onclick={() => deleteWebhook(hook.id)} title="Delete">
									<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.5"/></svg>
								</button>
							</div>
						{/each}
					</div>
				{:else}
					<p class="section-hint mono">No webhooks configured.</p>
				{/if}
				<div class="webhook-form">
					<input type="url" class="input mono" bind:value={newWebhookUrl} placeholder="https://hooks.example.com/..." />
					<div class="event-toggles">
						{#each ['job_completed', 'job_failed'] as ev}
							<label class="event-toggle mono">
								<input type="checkbox" checked={newWebhookEvents.has(ev)} onchange={() => toggleWebhookEvent(ev)} />
								{ev}
							</label>
						{/each}
					</div>
					<button class="btn-primary mono" onclick={addWebhook} disabled={!newWebhookUrl.trim()}>ADD WEBHOOK</button>
				</div>
			</section>
		{/if}

		<!-- IP Allowlist -->
		{#if isOwner()}
			<section class="section-card">
				<h2 class="section-title mono">IP ALLOWLIST</h2>
				{#if ipAllowlist.length === 0}
					<p class="section-hint mono">No restrictions — all IPs allowed.</p>
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
				<div class="form-row">
					<input type="text" class="input mono" bind:value={newCidr} placeholder="192.168.1.0/24" />
					<button class="btn-primary mono" onclick={addCidr}>ADD</button>
				</div>
			</section>
		{/if}

		<!-- Danger zone -->
		{#if isOwner() && !org.personal}
			<section class="section-card danger">
				<button class="btn-danger mono" onclick={deleteOrg}>DELETE ORGANIZATION</button>
			</section>
		{/if}
	{/if}
</div>

<style>
	.page { padding: var(--sp-5) var(--sp-6); display: flex; flex-direction: column; gap: var(--sp-4); max-width: 700px; }
	.loading { text-align: center; padding: var(--sp-8); color: var(--text-tertiary); font-size: 12px; }

	.page-header { display: flex; flex-direction: column; gap: var(--sp-1); }
	.back-link { font-size: 11px; color: var(--text-tertiary); text-decoration: none; }
	.back-link:hover { color: var(--accent); }
	.title-row { display: flex; align-items: center; gap: var(--sp-2); }
	.page-title { font-family: var(--font-sans); font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
	.badge { font-size: 9px; letter-spacing: 0.06em; padding: 2px 6px; border-radius: 3px; }
	.badge.personal { background: rgba(255, 242, 3, 0.1); color: var(--accent); }
	.badge.team { background: rgba(0, 154, 218, 0.1); color: var(--secondary); }

	.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: var(--sp-3); }
	.stat-card {
		background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md);
		padding: var(--sp-3); display: flex; flex-direction: column; gap: var(--sp-1);
	}
	.stat-label { font-size: 9px; letter-spacing: 0.1em; color: var(--text-tertiary); }
	.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); }
	.stat-value.positive { color: var(--state-complete); }
	.stat-value.negative { color: var(--state-error); }
	.stat-detail { font-size: 10px; color: var(--text-tertiary); }

	.storage-bar { height: 4px; background: var(--surface-4); border-radius: 2px; overflow: hidden; margin-top: var(--sp-1); }
	.storage-fill { height: 100%; background: var(--accent); border-radius: 2px; }

	.section-card {
		background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md);
		padding: var(--sp-4); display: flex; flex-direction: column; gap: var(--sp-3);
	}
	.section-card.danger { border-color: rgba(255, 82, 82, 0.2); }
	.section-title { font-size: 10px; letter-spacing: 0.1em; color: var(--text-tertiary); font-weight: 600; }
	.section-hint { font-size: 12px; color: var(--text-tertiary); }

	.member-list { display: flex; flex-direction: column; gap: var(--sp-1); }
	.member-row { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-1) 0; }
	.member-email { flex: 1; font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; }
	.role-badge { font-size: 9px; letter-spacing: 0.06em; padding: 2px 6px; border-radius: 3px; }
	.role-badge[data-role="owner"] { background: rgba(255, 242, 3, 0.12); color: var(--accent); }
	.role-badge[data-role="admin"] { background: rgba(206, 147, 216, 0.12); color: var(--state-masked); }
	.role-badge[data-role="member"] { background: rgba(93, 216, 121, 0.12); color: var(--state-complete); }

	.select-sm {
		font-size: 11px; padding: 3px 6px; background: var(--surface-3); border: 1px solid var(--border);
		border-radius: 4px; color: var(--text-secondary); cursor: pointer;
	}
	.btn-icon {
		background: none; border: none; cursor: pointer; color: var(--text-tertiary);
		padding: 2px; border-radius: 3px; display: flex; align-items: center;
	}
	.btn-icon:hover { color: var(--state-error); }

	.form-row { display: flex; gap: var(--sp-2); align-items: center; }
	.form-error { font-size: 11px; color: var(--state-error); padding: var(--sp-1) var(--sp-2); background: rgba(255, 82, 82, 0.08); border-radius: 4px; }
	.input {
		flex: 1; padding: 7px 10px; background: var(--surface-3); border: 1px solid var(--border);
		border-radius: 6px; color: var(--text-primary); font-size: 12px; outline: none;
	}
	.input:focus { border-color: var(--accent); }
	.input::placeholder { color: var(--text-tertiary); }
	.btn-primary {
		padding: 6px 14px; font-size: 10px; font-weight: 600; letter-spacing: 0.06em;
		background: var(--accent); color: #000; border: none; border-radius: var(--radius-sm);
		cursor: pointer; white-space: nowrap;
	}
	.btn-primary:hover { background: #fff; }
	.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
	.btn-danger {
		padding: 8px 16px; font-size: 11px; letter-spacing: 0.06em;
		background: transparent; border: 1px solid rgba(255, 82, 82, 0.3); color: var(--state-error);
		border-radius: var(--radius-sm); cursor: pointer;
	}
	.btn-danger:hover { background: rgba(255, 82, 82, 0.1); }

	.toggle-row { display: flex; align-items: flex-start; gap: var(--sp-2); cursor: pointer; }
	.toggle { accent-color: var(--accent); margin-top: 3px; }
	.toggle-info { display: flex; flex-direction: column; gap: 2px; font-size: 13px; color: var(--text-primary); }
	.toggle-hint { font-size: 11px; color: var(--text-tertiary); }

	.webhook-list { display: flex; flex-direction: column; gap: var(--sp-2); }
	.webhook-row { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-1) 0; }
	.webhook-url { font-size: 12px; color: var(--text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; }
	.webhook-events { font-size: 10px; color: var(--text-tertiary); }
	.webhook-form { display: flex; flex-direction: column; gap: var(--sp-2); border-top: 1px solid var(--border); padding-top: var(--sp-2); }
	.event-toggles { display: flex; gap: var(--sp-2); }
	.event-toggle { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
	.event-toggle input { accent-color: var(--accent); }

	.cidr-list { display: flex; flex-direction: column; gap: var(--sp-1); }
	.cidr-row { display: flex; align-items: center; gap: var(--sp-2); font-size: 12px; color: var(--text-secondary); }
</style>
