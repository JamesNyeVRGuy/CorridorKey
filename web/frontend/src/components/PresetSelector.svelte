<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { toast } from '$lib/stores/toasts';
	import type { Preset, InferenceParams, OutputConfig } from '$lib/api';

	let {
		onApply,
		currentParams,
		currentOutputConfig,
		allowSetDefault = false,
	}: {
		onApply: (params: InferenceParams, outputConfig: OutputConfig) => void;
		currentParams: InferenceParams;
		currentOutputConfig: OutputConfig;
		allowSetDefault?: boolean;
	} = $props();

	let presets = $state<Preset[]>([]);
	let selectedId = $state<string>('');
	let loading = $state(false);
	let saving = $state(false);
	let editing = $state(false);
	let settingDefault = $state(false);
	let showSaveDialog = $state(false);
	let showEditDialog = $state(false);
	let saveName = $state('');
	let saveDesc = $state('');
	let editName = $state('');
	let editDesc = $state('');
	let error = $state<string | null>(null);

	async function loadPresets() {
		loading = true;
		let defaultId = '';
		try {
			const res = await api.presets.list();
			presets = res.presets;
			const def = presets.find((p) => p.is_default);
			if (def) {
				defaultId = def.id;
				onApply({ ...def.params }, { ...def.output_config });
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			// Batch loading=false and selectedId together so Svelte creates the
			// <select> with its <option> children already present in the same DOM flush.
			loading = false;
			if (defaultId) selectedId = defaultId;
		}
	}

	function applyPreset() {
		const preset = presets.find((p) => p.id === selectedId);
		if (!preset) {
			toast.warning('Preset no longer exists — refreshing list.');
			selectedId = '';
			loadPresets();
			return;
		}
		onApply(
			{ ...preset.params },
			{ ...preset.output_config }
		);
	}

	async function saveAsPreset() {
		if (!saveName.trim()) return;
		saving = true;
		error = null;
		try {
			const created = await api.presets.create({
				name: saveName.trim(),
				description: saveDesc.trim(),
				params: currentParams,
				output_config: currentOutputConfig,
			});
			presets = [...presets, created];
			selectedId = created.id;
			showSaveDialog = false;
			saveName = '';
			saveDesc = '';
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			saving = false;
		}
	}

	async function editPreset() {
		if (!editName.trim() || !selectedId) return;
		editing = true;
		error = null;
		try {
			const updated = await api.presets.update(selectedId, {
				name: editName.trim(),
				description: editDesc.trim(),
			});
			presets = presets.map((p) => (p.id === updated.id ? updated : p));
			showEditDialog = false;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			editing = false;
		}
	}

	async function setDefault(id: string) {
		settingDefault = true;
		error = null;
		try {
			await api.presets.update(id, { is_default: true });
			// Update local list: clear all is_default, set the chosen one, re-sort
			presets = presets
				.map((p) => ({ ...p, is_default: p.id === id }))
				.sort((a, b) => (a.is_default === b.is_default ? a.name.localeCompare(b.name) : a.is_default ? -1 : 1));
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			settingDefault = false;
		}
	}

	async function deletePreset(id: string) {
		try {
			await api.presets.delete(id);
			presets = presets.filter((p) => p.id !== id);
			if (selectedId === id) {
				selectedId = '';
				showEditDialog = false;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	onMount(loadPresets);
</script>

<div class="preset-panel">
	<h3 class="section-title mono">PRESETS</h3>

	<div class="preset-row">
		{#if loading}
			<div class="skeleton skeleton-select"></div>
			<div class="skeleton skeleton-btn"></div>
		{:else}
		<select
			class="preset-select"
			bind:value={selectedId}
			disabled={loading}
		>
			<option value="">Select Preset</option>
			{#each presets as preset}
				<option value={preset.id}>{preset.name}</option>
			{/each}
		</select>

		<button
			class="btn-sm"
			onclick={applyPreset}
			disabled={!selectedId}
			title="Load preset"
		>
			Load
		</button>
		{/if}
	</div>

	{#if selectedId}
		{@const selected = presets.find((p) => p.id === selectedId)}
		{#if showEditDialog}
			<div class="save-dialog">
				<input
					class="save-input"
					type="text"
					placeholder="Preset name"
					bind:value={editName}
					maxlength={100}
				/>
				<input
					class="save-input"
					type="text"
					placeholder="Description (optional)"
					bind:value={editDesc}
					maxlength={500}
				/>
				<div class="save-actions">
					<button class="btn-sm" onclick={editPreset} disabled={editing || !editName.trim()}>
						{editing ? 'Saving…' : 'Save'}
					</button>
					<button class="btn-sm btn-muted" onclick={() => { showEditDialog = false; }}>
						Cancel
					</button>
				</div>
			</div>
		{:else}
			{#if selected?.description}
				<p class="preset-desc">{selected.description}</p>
			{/if}
			<div class="preset-actions">
				<button
					class="btn-sm btn-muted"
					onclick={() => { if (selected) { editName = selected.name; editDesc = selected.description; showEditDialog = true; } }}
					title="Rename this preset"
				>
					Rename
				</button>
				{#if selected?.is_default}
					<span class="default-badge" title="This is the default preset">★ Default</span>
				{:else if allowSetDefault}
					<button
						class="btn-sm btn-muted"
						onclick={() => { if (selected) setDefault(selected.id); }}
						disabled={settingDefault}
						title="Load this preset automatically on page open"
					>
						{settingDefault ? '…' : 'Set Default'}
					</button>
				{/if}
				<button
					class="btn-sm btn-danger"
					onclick={() => { if (selected) deletePreset(selected.id); }}
					title="Delete this preset"
				>
					Delete
				</button>
			</div>
		{/if}
	{/if}

	<div class="save-row">
		{#if showSaveDialog}
			<div class="save-dialog">
				<input
					class="save-input"
					type="text"
					placeholder="Preset name"
					bind:value={saveName}
					maxlength={100}
				/>
				<input
					class="save-input"
					type="text"
					placeholder="Description (optional)"
					bind:value={saveDesc}
					maxlength={500}
				/>
				<div class="save-actions">
					<button class="btn-sm" onclick={saveAsPreset} disabled={saving || !saveName.trim()}>
						{saving ? 'Saving…' : 'Save'}
					</button>
					<button class="btn-sm btn-muted" onclick={() => { showSaveDialog = false; }}>
						Cancel
					</button>
				</div>
			</div>
		{:else}
			<button class="btn-sm btn-muted" onclick={() => { showSaveDialog = true; }}>
				Save Current as Preset
			</button>
		{/if}
	</div>

	{#if error}
		<p class="preset-error">{error}</p>
	{/if}
</div>

<style>
	.preset-panel {
		display: flex;
		flex-direction: column;
		gap: var(--sp-3);
		overflow: hidden;
	}

	.section-title {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.12em;
		color: var(--accent);
		padding-bottom: var(--sp-2);
		border-bottom: 1px solid var(--border);
	}

	.preset-row {
		display: flex;
		gap: var(--sp-2);
		align-items: center;
	}

	.preset-select {
		flex: 1;
		min-width: 0;
		padding: 8px 28px 8px 14px;
		font-family: inherit;
		font-size: 11px;
		font-weight: 600;
		text-overflow: ellipsis;
		overflow: hidden;
		white-space: nowrap;
		background-color: var(--surface-3);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		cursor: pointer;
		appearance: none;
		-webkit-appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23888'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 10px center;
		padding-right: 28px;
		transition: background-color 0.15s, border-color 0.15s;
	}

	.preset-select:hover {
		background-color: var(--surface-2);
		border-color: var(--text-tertiary);
	}

	.preset-select:focus {
		border-color: var(--accent);
		outline: none;
	}

	.preset-actions {
		display: flex;
		gap: var(--sp-2);
		align-items: center;
		flex-wrap: wrap;
	}

	.default-badge {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.06em;
		color: var(--accent);
		padding: 4px 8px;
		border: 1px solid var(--accent-muted, color-mix(in srgb, var(--accent) 30%, transparent));
		border-radius: var(--radius-sm);
		white-space: nowrap;
	}

	.preset-desc {
		font-size: 11px;
		color: var(--text-tertiary);
		margin: 0;
		line-height: 1.4;
		overflow-wrap: break-word;
		word-break: break-word;
	}

	.save-row {
		margin-top: var(--sp-1);
	}

	.save-dialog {
		display: flex;
		flex-direction: column;
		gap: var(--sp-2);
	}

	.save-input {
		width: 100%;
		min-width: 0;
		padding: 8px 14px;
		font-family: inherit;
		font-size: 11px;
		background: var(--surface-3);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-primary);
		outline: none;
		transition: all 0.15s;
	}

	.save-input:focus {
		border-color: var(--accent);
	}

	.save-actions {
		display: flex;
		gap: var(--sp-2);
	}

	.btn-sm {
		padding: 8px 14px;
		font-family: inherit;
		font-size: 11px;
		font-weight: 600;
		background: var(--accent);
		color: #000;
		border: 1px solid var(--accent);
		border-radius: var(--radius-sm);
		cursor: pointer;
		white-space: nowrap;
		transition: all 0.15s;
	}

	.btn-sm:hover {
		background: #fff;
		border-color: #fff;
	}

	.btn-sm:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.btn-muted {
		background: var(--surface-4);
		color: var(--text-primary);
		border: 1px solid var(--border);
	}

	.btn-muted:hover {
		background: var(--surface-3);
		border-color: var(--text-tertiary);
	}

	.btn-danger {
		background: transparent;
		color: var(--state-error);
		border: 1px solid var(--state-error);
	}

	.btn-danger:hover {
		background: rgba(255, 82, 82, 0.1);
	}

	.preset-error {
		font-size: 11px;
		color: var(--state-error);
		margin: 0;
	}

	.skeleton {
		border-radius: var(--radius-sm);
		background: linear-gradient(
			90deg,
			var(--surface-3) 25%,
			var(--surface-2) 50%,
			var(--surface-3) 75%
		);
		background-size: 200% 100%;
		animation: shimmer 1.4s infinite;
	}

	.skeleton-select {
		flex: 1;
		height: 35px;
	}

	.skeleton-btn {
		width: 52px;
		height: 35px;
		flex-shrink: 0;
	}

	@keyframes shimmer {
		0%   { background-position: 200% 0; }
		100% { background-position: -200% 0; }
	}
</style>
