-- Add SET search_path = public to all SECURITY DEFINER functions (M-23)
ALTER FUNCTION public.credit_reserve SET search_path = public;
ALTER FUNCTION public.credit_release SET search_path = public;
ALTER FUNCTION public.credit_commit SET search_path = public;
ALTER FUNCTION public.sum_credit_balance SET search_path = public;
ALTER FUNCTION public.insert_comment_atomic SET search_path = public;
ALTER FUNCTION public.persist_reaction_atomic SET search_path = public;
ALTER FUNCTION public.handle_checkout_credit_atomic SET search_path = public;

-- DOWN:
ALTER FUNCTION public.credit_reserve RESET search_path;
ALTER FUNCTION public.credit_release RESET search_path;
ALTER FUNCTION public.credit_commit RESET search_path;
ALTER FUNCTION public.sum_credit_balance RESET search_path;
ALTER FUNCTION public.insert_comment_atomic RESET search_path;
ALTER FUNCTION public.persist_reaction_atomic RESET search_path;
ALTER FUNCTION public.handle_checkout_credit_atomic RESET search_path;
