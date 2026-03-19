/**
 * useBuckets — loads and manages the bucket list.
 *
 * Syncs the bucket list with the global Zustand store so both the
 * upload screen and chat screen share the same data without double-fetching.
 */

import { useState, useEffect, useCallback } from "react";
import { bucketsApi } from "../api/buckets";
import type { Bucket, BucketCreateRequest } from "../types";
import { useAppStore } from "../store/appStore";
import toast from "react-hot-toast";

export function useBuckets() {
  const { buckets, setBuckets, addBucket, removeBucket } = useAppStore();
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  const fetchBuckets = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await bucketsApi.list();
      setBuckets(data);
    } catch {
      // silently fail — buckets may not exist yet
    } finally {
      setIsLoading(false);
    }
  }, [setBuckets]);

  useEffect(() => {
    if (buckets.length === 0) {
      fetchBuckets();
    }
  }, [buckets.length, fetchBuckets]);

  const createBucket = useCallback(
    async (request: BucketCreateRequest): Promise<Bucket | null> => {
      setIsCreating(true);
      try {
        const bucket = await bucketsApi.create(request);
        addBucket(bucket);
        toast.success(`Bucket "${bucket.name}" created.`);
        return bucket;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to create bucket";
        toast.error(msg);
        return null;
      } finally {
        setIsCreating(false);
      }
    },
    [addBucket]
  );

  const deleteBucket = useCallback(
    async (bucketId: string): Promise<boolean> => {
      try {
        await bucketsApi.delete(bucketId);
        removeBucket(bucketId);
        toast.success("Bucket deleted.");
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to delete bucket";
        toast.error(msg);
        return false;
      }
    },
    [removeBucket]
  );

  const assignDocument = useCallback(
    async (bucketId: string, documentId: string): Promise<boolean> => {
      try {
        await bucketsApi.assignDocument(bucketId, documentId);
        // Refresh bucket list to get updated document_count
        await fetchBuckets();
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to assign document";
        toast.error(msg);
        return false;
      }
    },
    [fetchBuckets]
  );

  return {
    buckets,
    isLoading,
    isCreating,
    fetchBuckets,
    createBucket,
    deleteBucket,
    assignDocument,
  };
}
