-- 日报统计
SELECT a.name, COUNT(*) AS cnt
FROM orders a /* 关联明细 */
WHERE a.status = 'DONE' -- 只算完成
GROUP BY a.name;

/*
多行说明
*/
