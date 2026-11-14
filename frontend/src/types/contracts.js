/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,job_id:number,attempt_no:number,worker_id:string,status:string,reason:string,error:string,started_at:number,heartbeat_at:number,finished_at:?number}} JobAttempt */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,error:string,approved:boolean,attempt_no:number,worker_id:?string,heartbeat_at:?number,queued_at:?number,taken_over:boolean,attempts:JobAttempt[]}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
export {};
