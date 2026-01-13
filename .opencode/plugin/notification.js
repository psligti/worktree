export const NotificationPlugin = async ({ $, worktree }) => {
  return {
    event: async ({ event }) => {
      const marker = `${worktree}/.opencode/idle`
      if (event.type === "session.idle") {
        await $`mkdir -p ${worktree}/.opencode && echo idle > ${marker}`
      }
      if (event.type === "session.active") {
        await $`rm -f ${marker}`
      }
    },
  }
}