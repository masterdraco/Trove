<script lang="ts">
  import NotificationsPanel from "../settings/NotificationsPanel.svelte";
</script>

<div class="max-w-3xl space-y-6">
  <div>
    <h2 class="text-xl font-semibold">Notifications</h2>
    <p class="mt-1 text-sm text-muted-foreground">
      Configure where Trove sends alerts when tasks grab releases, downloads complete, or errors occur.
    </p>
  </div>

  <NotificationsPanel />
</div>
