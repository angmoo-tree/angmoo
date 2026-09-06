export type TreeCategory = "notice" | "bug" | "suggestion" | "question" | "free";


export type TreeAuthorRead = {
  id: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
};


export type TreeRelatedCharacterRead = {
  id: string;
  name: string;
  handle: string | null;
  avatar_url: string | null;
};


export type TreePostSummary = {
  id: string;
  category: TreeCategory;
  title: string;
  body: string;
  author: TreeAuthorRead;
  related_character: TreeRelatedCharacterRead | null;
  comment_count: number;
  created_at: string;
  updated_at: string;
};


export type TreeCommentRead = {
  id: number;
  post_id: string;
  author: TreeAuthorRead;
  content: string;
  created_at: string;
};


export type TreePostDetail = TreePostSummary & {
  comments: TreeCommentRead[];
};


export type TreeFeedPage = {
  items: TreePostSummary[];
  next_cursor: string | null;
};
