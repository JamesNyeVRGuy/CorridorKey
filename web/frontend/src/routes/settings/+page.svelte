<script lang="ts">
	import { onMount } from 'svelte';
	import { defaultParams, defaultOutputConfig, autoExtractFrames, autoShard } from '$lib/stores/settings';
	import { api } from '$lib/api';
	import { toast } from '$lib/stores/toasts';
	import { getStoredUser } from '$lib/auth';
	import InferenceForm from '../../components/InferenceForm.svelte';

	let isAdmin = $state(false);
	let activeTab = $state<'processing' | 'account'>('processing');
	let allowSharedNodes = $state(true);
	let activeOrgId = $state('');

	// Account
	let userName = $state('');
	let userEmail = $state('');
	let userTier = $state('');

	async function loadOrgPreferences() {
		try {
			const { getActiveOrgId } = await import('$lib/auth');
			activeOrgId = getActiveOrgId() || '';
			if (!activeOrgId) return;
			const token = localStorage.getItem('ck:auth_token');
			const res = await fetch(`/api/orgs/${activeOrgId}/preferences`, {
				headers: token ? { 'Authorization': `Bearer ${token}` } : {},
			});
			if (res.ok) {
				const data = await res.json();
				allowSharedNodes = data.allow_shared_nodes ?? true;
			}
		} catch { /* ignore */ }
	}

	async function saveSharedNodesPref() {
		if (!activeOrgId) return;
		try {
			const token = localStorage.getItem('ck:auth_token');
			await fetch(`/api/orgs/${activeOrgId}/preferences`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
				body: JSON.stringify({ allow_shared_nodes: allowSharedNodes }),
			});
		} catch { /* ignore */ }
	}

	onMount(() => {
		const user = getStoredUser();
		isAdmin = user?.tier === 'platform_admin';
		userName = user?.name || '';
		userEmail = user?.email || '';
		userTier = user?.tier || '';
		loadOrgPreferences();
	});
</script>

<svelte:head>
	<title>Settings — CorridorKey</title>
</svelte:head>

<div class="page">
	<div class="page-header">
		<h1 class="page-title">Settings</h1>
	</div>

	<!-- Tabs -->
	<div class="tabs">
		<button class="tab mono" class:active={activeTab === 'processing'} onclick={() => activeTab = 'processing'}>Processing</button>
		<button class="tab mono" class:active={activeTab === 'account'} onclick={() => activeTab = 'account'}>Account</button>
		{#if isAdmin}
			<a href="/admin/system" class="tab mono tab-link">Server Config &rarr;</a>
		{/if}
	</div>

	<div class="tab-content">
		{#if activeTab === 'processing'}
			<!-- Upload & processing behavior -->
			<section class="card">
				<h2 class="card-title mono">PROCESSING</h2>
				<label class="toggle-field">
					<input type="checkbox" bind:checked={$autoExtractFrames} class="toggle" />
					<div class="toggle-label">
						<span>Auto-extract frames on video upload</span>
						<span class="toggle-hint">Uploading a video automatically queues frame extraction.</span>
					</div>
				</label>
				<label class="toggle-field">
					<input type="checkbox" bind:checked={$autoShard} class="toggle" />
					<div class="toggle-label">
						<span>Auto-shard inference across GPUs</span>
						<span class="toggle-hint">Inference jobs automatically split across all available GPUs and nodes.</span>
					</div>
				</label>
				<label class="toggle-field">
					<input type="checkbox" bind:checked={allowSharedNodes} onchange={saveSharedNodesPref} class="toggle" />
					<div class="toggle-label">
						<span>Allow shared community nodes</span>
						<span class="toggle-hint">Your jobs can be processed by community-contributed GPU nodes. Disable to only use your org's private nodes.</span>
					</div>
				</label>
			</section>

			<!-- Default parameters -->
			<section class="card">
				<h2 class="card-title mono">DEFAULT PARAMETERS</h2>
				<p class="card-desc">Pre-fill values for the inference form.</p>
				<InferenceForm bind:params={$defaultParams} bind:outputConfig={$defaultOutputConfig} allowSetDefault={true} />
			</section>

			<!-- Help -->
			<section class="card">
				<h2 class="card-title mono">HELP</h2>
				<div class="help-row">
					<div class="help-info">
						<span class="help-label">Welcome Guide</span>
						<span class="help-hint">Show the pipeline walkthrough again.</span>
					</div>
					<button class="btn-secondary mono" onclick={() => { localStorage.removeItem('ck:tour'); window.location.reload(); }}>
						Restart Tour
					</button>
				</div>
			</section>

		{:else if activeTab === 'account'}
			<section class="card">
				<h2 class="card-title mono">PROFILE</h2>
				<div class="profile-rows">
					<div class="profile-row">
						<span class="profile-label">Name</span>
						<span class="profile-value">{userName || '—'}</span>
					</div>
					<div class="profile-row">
						<span class="profile-label">Email</span>
						<span class="profile-value mono">{userEmail || '—'}</span>
					</div>
					<div class="profile-row">
						<span class="profile-label">Tier</span>
						<span class="tier-badge mono" data-tier={userTier}>{userTier}</span>
					</div>
				</div>
				<a href="/profile" class="btn-secondary mono">Edit Profile</a>
			</section>

			<section class="card">
				<h2 class="card-title mono">KEYBOARD SHORTCUTS</h2>
				<div class="shortcut-list mono">
					<div class="shortcut-row"><span class="shortcut-key">?</span><span>Show keyboard shortcuts</span></div>
					<div class="shortcut-row"><span class="shortcut-key">← →</span><span>Previous / next frame</span></div>
					<div class="shortcut-row"><span class="shortcut-key">Space</span><span>Play / pause video preview</span></div>
					<div class="shortcut-row"><span class="shortcut-key">W</span><span>Toggle wipe comparison mode</span></div>
					<div class="shortcut-row"><span class="shortcut-key">1-5</span><span>Switch output pass</span></div>
				</div>
			</section>
		{/if}
	</div>
</div>

<style>
	.page { padding: var(--sp-5) var(--sp-6); display: flex; flex-direction: column; gap: var(--sp-4); max-width: 580px; }

	.page-header { display: flex; align-items: center; justify-content: space-between; }
	.page-title { font-family: var(--font-sans); font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }

	/* Tabs */
	.tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); }
	.tab {
		padding: var(--sp-2) var(--sp-4); font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
		color: var(--text-tertiary); background: none; border: none; border-bottom: 2px solid transparent;
		cursor: pointer; transition: all 0.15s;
	}
	.tab:hover { color: var(--text-secondary); }
	.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
	.tab-link { text-decoration: none; margin-left: auto; color: var(--text-tertiary); }
	.tab-link:hover { color: var(--secondary); }

	.tab-content { display: flex; flex-direction: column; gap: var(--sp-4); }

	.card {
		display: flex; flex-direction: column; gap: var(--sp-4);
		padding: var(--sp-5); background: var(--surface-2);
		border: 1px solid var(--border); border-radius: var(--radius-lg);
	}
	.card-title { font-size: 10px; font-weight: 600; letter-spacing: 0.12em; color: var(--accent); }
	.card-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.4; }

	/* Toggles */
	.toggle-field { display: flex; align-items: flex-start; gap: var(--sp-3); cursor: pointer; }
	.toggle {
		-webkit-appearance: none; appearance: none; width: 32px; height: 16px;
		border-radius: 8px; background: var(--surface-4); position: relative;
		cursor: pointer; transition: background 0.15s; flex-shrink: 0; margin-top: 2px;
	}
	.toggle::after {
		content: ''; position: absolute; top: 2px; left: 2px;
		width: 12px; height: 12px; border-radius: 50%; background: var(--text-tertiary);
		transition: transform 0.15s, background 0.15s;
	}
	.toggle:checked { background: var(--accent-muted); }
	.toggle:checked::after { transform: translateX(16px); background: var(--accent); }
	.toggle-label { display: flex; flex-direction: column; gap: 2px; font-size: 13px; color: var(--text-primary); }
	.toggle-hint { font-size: 12px; color: var(--text-tertiary); line-height: 1.4; }

	/* Help */
	.help-row { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-3); }
	.help-info { display: flex; flex-direction: column; gap: 2px; }
	.help-label { font-size: 13px; font-weight: 500; color: var(--text-primary); }
	.help-hint { font-size: 12px; color: var(--text-tertiary); }

	.btn-secondary {
		padding: 8px 14px; font-size: 11px; font-weight: 600;
		background: var(--surface-4); color: var(--text-primary); border: 1px solid var(--border);
		border-radius: var(--radius-sm); cursor: pointer; transition: all 0.15s;
		align-self: flex-start; text-decoration: none;
	}
	.btn-secondary:hover { background: var(--surface-3); border-color: var(--text-tertiary); }

	/* Profile */
	.profile-rows { display: flex; flex-direction: column; gap: var(--sp-2); }
	.profile-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
	.profile-label { color: var(--text-tertiary); }
	.profile-value { color: var(--text-primary); }

	.tier-badge { font-size: 10px; padding: 2px 8px; border-radius: 3px; letter-spacing: 0.06em; }
	.tier-badge[data-tier="pending"] { background: rgba(255, 242, 3, 0.12); color: var(--accent); }
	.tier-badge[data-tier="member"] { background: rgba(61, 184, 255, 0.12); color: var(--state-ready); }
	.tier-badge[data-tier="contributor"] { background: rgba(93, 216, 121, 0.12); color: var(--state-complete); }
	.tier-badge[data-tier="org_admin"] { background: rgba(206, 147, 216, 0.12); color: var(--state-masked); }
	.tier-badge[data-tier="platform_admin"] { background: rgba(255, 82, 82, 0.12); color: var(--state-error); }

	/* Shortcuts */
	.shortcut-list { display: flex; flex-direction: column; gap: var(--sp-2); }
	.shortcut-row { display: flex; align-items: center; gap: var(--sp-3); font-size: 12px; color: var(--text-secondary); }
	.shortcut-key {
		min-width: 36px; text-align: center; padding: 2px 6px;
		background: var(--surface-4); border: 1px solid var(--border); border-radius: 4px;
		font-size: 11px; color: var(--text-primary);
	}
</style>
