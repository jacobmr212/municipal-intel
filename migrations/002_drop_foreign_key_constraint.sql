-- Drop foreign key constraint temporarily to allow assessment creation
-- The constraint may be preventing inserts if user IDs don't match exactly

ALTER TABLE "Assessment" DROP CONSTRAINT IF EXISTS fk_user;
