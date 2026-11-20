import type { VideoLook } from "@/types/api";

/** Video post-processing request fields. Sent only when set, so plain requests stay exactly as before. */
export function postFields(post: { look: VideoLook; enhance: boolean } | undefined): { look?: VideoLook; enhance?: boolean } {
  return {
    ...(post && post.look !== "none" ? { look: post.look } : {}),
    ...(post?.enhance ? { enhance: true } : {}),
  };
}
