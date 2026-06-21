
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `academic_calendar_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `category` enum('holiday','exam_week','event') COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `department_id` int DEFAULT NULL,
  `semester` int DEFAULT NULL,
  `created_by` int DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `created_by` (`created_by`),
  KEY `department_id` (`department_id`),
  KEY `ix_academic_calendar_events_college_id` (`college_id`),
  KEY `ix_calendar_events_college_dates` (`college_id`,`start_date`,`end_date`),
  KEY `ix_calendar_events_college_scope` (`college_id`,`department_id`,`semester`),
  CONSTRAINT `academic_calendar_events_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`),
  CONSTRAINT `academic_calendar_events_ibfk_2` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `fk_calendar_events_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `assignment_submissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `content_id` int NOT NULL,
  `student_id` int NOT NULL,
  `submission_text` text COLLATE utf8mb4_unicode_ci,
  `file_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('submitted','reviewed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `submitted_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `graded_at` datetime DEFAULT NULL,
  `marks_awarded` int DEFAULT NULL,
  `feedback` text COLLATE utf8mb4_unicode_ci,
  `college_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_assignment_submission_content_student` (`content_id`,`student_id`),
  KEY `student_id` (`student_id`),
  KEY `ix_assignment_submissions_college_id` (`college_id`),
  KEY `ix_assignment_submissions_college_content_status` (`college_id`,`content_id`,`status`),
  KEY `ix_assignment_submissions_college_student_status` (`college_id`,`student_id`,`status`),
  CONSTRAINT `assignment_submissions_ibfk_1` FOREIGN KEY (`content_id`) REFERENCES `teacher_contents` (`id`),
  CONSTRAINT `assignment_submissions_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`),
  CONSTRAINT `fk_assignment_submissions_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `attendance_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` int NOT NULL,
  `student_id` int NOT NULL,
  `status` enum('present','absent','late') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `marked_at` datetime DEFAULT NULL,
  `liveness_verified` tinyint(1) DEFAULT NULL,
  `confidence_score` float DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_session_student` (`session_id`,`student_id`),
  KEY `student_id` (`student_id`),
  KEY `ix_attendance_records_college_id` (`college_id`),
  KEY `ix_attendance_records_college_student` (`college_id`,`student_id`),
  KEY `ix_attendance_records_college_session_status` (`college_id`,`session_id`,`status`),
  CONSTRAINT `attendance_records_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `attendance_sessions` (`id`),
  CONSTRAINT `attendance_records_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`),
  CONSTRAINT `fk_attendance_records_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=589 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `attendance_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `subject_id` int NOT NULL,
  `teacher_id` int NOT NULL,
  `date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time DEFAULT NULL,
  `status` enum('active','completed','cancelled') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `subject_id` (`subject_id`),
  KEY `teacher_id` (`teacher_id`),
  KEY `ix_attendance_sessions_college_id` (`college_id`),
  KEY `ix_attendance_sessions_college_status_date` (`college_id`,`status`,`date`),
  KEY `ix_attendance_sessions_college_teacher_status` (`college_id`,`teacher_id`,`status`),
  CONSTRAINT `attendance_sessions_ibfk_1` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`),
  CONSTRAINT `attendance_sessions_ibfk_2` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`),
  CONSTRAINT `fk_attendance_sessions_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=50 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `class_alerts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `slot_id` int NOT NULL,
  `alert_date` date NOT NULL,
  `sent_at` datetime DEFAULT NULL,
  `recipient_count` int DEFAULT NULL,
  `triggered_by` enum('auto','manual') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_alert_per_day` (`slot_id`,`alert_date`),
  KEY `ix_class_alerts_college_id` (`college_id`),
  KEY `ix_class_alerts_college_date` (`college_id`,`alert_date`),
  CONSTRAINT `class_alerts_ibfk_1` FOREIGN KEY (`slot_id`) REFERENCES `timetable_slots` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_class_alerts_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `classroom_bookings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_id` int NOT NULL,
  `classroom_id` int NOT NULL,
  `department_id` int DEFAULT NULL,
  `semester` int DEFAULT NULL,
  `title` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `booking_type` enum('class','exam','event','other') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'class',
  `is_recurring` tinyint(1) NOT NULL DEFAULT '0',
  `booking_date` date DEFAULT NULL,
  `day_of_week` int DEFAULT NULL,
  `valid_from` date DEFAULT NULL,
  `valid_until` date DEFAULT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_by` int NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  KEY `classroom_id` (`classroom_id`),
  KEY `department_id` (`department_id`),
  KEY `created_by` (`created_by`),
  KEY `ix_cb_college_classroom` (`college_id`,`classroom_id`),
  KEY `ix_cb_college_date` (`college_id`,`booking_date`),
  KEY `ix_cb_recurring_dow` (`college_id`,`is_recurring`,`day_of_week`),
  KEY `ix_cb_is_active` (`college_id`,`is_active`),
  CONSTRAINT `classroom_bookings_ibfk_1` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `classroom_bookings_ibfk_2` FOREIGN KEY (`classroom_id`) REFERENCES `classrooms` (`id`),
  CONSTRAINT `classroom_bookings_ibfk_3` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `classroom_bookings_ibfk_4` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `classrooms` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_id` int NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `capacity` int DEFAULT NULL,
  `room_type` enum('lecture_hall','lab','seminar','exam_hall','other') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'lecture_hall',
  `block` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_classroom_college_name` (`college_id`,`name`),
  KEY `ix_classrooms_college_active` (`college_id`,`is_active`),
  CONSTRAINT `classrooms_ibfk_1` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `college_feature_access` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_id` int NOT NULL,
  `feature_key` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_college_feature_access` (`college_id`,`feature_key`),
  KEY `ix_college_feature_access_college_enabled` (`college_id`,`enabled`),
  KEY `ix_college_feature_access_college_id` (`college_id`),
  CONSTRAINT `college_feature_access_ibfk_1` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=89 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `college_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `address` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `latitude` float DEFAULT NULL,
  `longitude` float DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `principal_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `principal_sign_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hod_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hod_sign_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `class_teacher_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `class_teacher_sign_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `college_id` int NOT NULL,
  `logo_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_college_settings_college_id` (`college_id`),
  CONSTRAINT `fk_college_settings_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `colleges` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subdomain` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL,
  `plan` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'free',
  `plan_expires_at` datetime DEFAULT NULL,
  `billing_notes` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_colleges_code` (`code`),
  UNIQUE KEY `uq_colleges_subdomain` (`subdomain`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `departments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_departments_college_code` (`college_id`,`code`),
  KEY `ix_departments_college_id` (`college_id`),
  CONSTRAINT `fk_departments_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `exams` (
  `id` int NOT NULL AUTO_INCREMENT,
  `subject_id` int NOT NULL,
  `title` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `exam_type` enum('quiz','mid_term','final','practical','assignment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `exam_date` date NOT NULL,
  `start_time` time DEFAULT NULL,
  `duration_mins` int DEFAULT NULL,
  `total_marks` float NOT NULL,
  `pass_marks` float DEFAULT NULL,
  `room` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `instructions` text COLLATE utf8mb4_unicode_ci,
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `subject_id` (`subject_id`),
  KEY `created_by` (`created_by`),
  KEY `ix_exams_college_id` (`college_id`),
  KEY `ix_exams_college_subject_date` (`college_id`,`subject_id`,`exam_date`),
  KEY `ix_exams_college_creator_date` (`college_id`,`created_by`,`exam_date`),
  KEY `ix_exams_is_deleted` (`is_deleted`),
  CONSTRAINT `exams_ibfk_1` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`),
  CONSTRAINT `exams_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `teachers` (`id`),
  CONSTRAINT `fk_exams_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `fee_payments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `fee_structure_id` int NOT NULL,
  `amount_paid` float NOT NULL,
  `payment_date` date NOT NULL,
  `transaction_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payment_method` enum('cash','bank_transfer','online','cheque') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('paid','partial','waived') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `receipt_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `remarks` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `recorded_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fee_payment` (`student_id`,`fee_structure_id`),
  UNIQUE KEY `uq_fee_payments_college_receipt_no` (`college_id`,`receipt_no`),
  KEY `fee_structure_id` (`fee_structure_id`),
  KEY `recorded_by` (`recorded_by`),
  KEY `ix_fee_payments_college_id` (`college_id`),
  KEY `ix_fee_payments_college_student_status` (`college_id`,`student_id`,`status`),
  KEY `ix_fee_payments_college_structure_status` (`college_id`,`fee_structure_id`,`status`),
  CONSTRAINT `fee_payments_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`),
  CONSTRAINT `fee_payments_ibfk_2` FOREIGN KEY (`fee_structure_id`) REFERENCES `fee_structures` (`id`),
  CONSTRAINT `fee_payments_ibfk_3` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`),
  CONSTRAINT `fk_fee_payments_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `fee_reminder_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_id` int NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '0',
  `days_before_due` int NOT NULL DEFAULT '7',
  `remind_on_due_date` tinyint(1) NOT NULL DEFAULT '1',
  `remind_overdue` tinyint(1) NOT NULL DEFAULT '1',
  `send_hour` int NOT NULL DEFAULT '8',
  `last_sent_at` datetime DEFAULT NULL,
  `updated_by` int DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fee_reminder_college` (`college_id`),
  KEY `updated_by` (`updated_by`),
  KEY `ix_fee_reminder_configs_college` (`college_id`),
  CONSTRAINT `fee_reminder_configs_ibfk_1` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fee_reminder_configs_ibfk_2` FOREIGN KEY (`updated_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `fee_structures` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `department_id` int DEFAULT NULL,
  `semester` int DEFAULT NULL,
  `academic_year` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` float NOT NULL,
  `due_date` date DEFAULT NULL,
  `description` varchar(300) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `department_id` (`department_id`),
  KEY `ix_fee_structures_college_id` (`college_id`),
  KEY `ix_fee_structures_college_department_semester_year` (`college_id`,`department_id`,`semester`,`academic_year`),
  KEY `ix_fee_structures_college_active_due` (`college_id`,`is_active`,`due_date`),
  CONSTRAINT `fee_structures_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `fk_fee_structures_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `id_card_templates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `logo_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `principal_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `principal_title` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `principal_signature_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `college_phone` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `college_website` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `card_color` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `accent_color` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `valid_years` int DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `map_lat` float DEFAULT NULL,
  `map_lng` float DEFAULT NULL,
  `college_image_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_id_card_templates_college_id` (`college_id`),
  CONSTRAINT `fk_id_card_templates_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `leave_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `leave_type` enum('student_subject','student_fullday','teacher') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'student_subject',
  `student_id` int DEFAULT NULL,
  `subject_id` int DEFAULT NULL,
  `teacher_id` int DEFAULT NULL,
  `approver_id` int DEFAULT NULL,
  `from_date` date NOT NULL,
  `to_date` date NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('pending','approved','rejected') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `teacher_remark` varchar(300) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `ref_number` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_leave_requests_college_ref_number` (`college_id`,`ref_number`),
  KEY `student_id` (`student_id`),
  KEY `subject_id` (`subject_id`),
  KEY `fk_lr_teacher` (`teacher_id`),
  KEY `fk_lr_approver` (`approver_id`),
  KEY `ix_leave_requests_college_id` (`college_id`),
  KEY `ix_leave_requests_college_status_created` (`college_id`,`status`,`created_at`),
  KEY `ix_leave_requests_college_student_status` (`college_id`,`student_id`,`status`),
  KEY `ix_leave_requests_college_teacher_status` (`college_id`,`teacher_id`,`status`),
  CONSTRAINT `fk_leave_requests_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `fk_lr_approver` FOREIGN KEY (`approver_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_lr_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`) ON DELETE SET NULL,
  CONSTRAINT `leave_requests_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`),
  CONSTRAINT `leave_requests_ibfk_2` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `marks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exam_id` int NOT NULL,
  `student_id` int NOT NULL,
  `marks_obtained` float DEFAULT NULL,
  `is_absent` tinyint(1) DEFAULT NULL,
  `remarks` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `entered_by` int DEFAULT NULL,
  `entered_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_exam_student` (`exam_id`,`student_id`),
  KEY `student_id` (`student_id`),
  KEY `entered_by` (`entered_by`),
  KEY `ix_marks_college_id` (`college_id`),
  KEY `ix_marks_college_student` (`college_id`,`student_id`),
  KEY `ix_marks_college_exam` (`college_id`,`exam_id`),
  CONSTRAINT `fk_marks_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `marks_ibfk_1` FOREIGN KEY (`exam_id`) REFERENCES `exams` (`id`),
  CONSTRAINT `marks_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`),
  CONSTRAINT `marks_ibfk_3` FOREIGN KEY (`entered_by`) REFERENCES `teachers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=85 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `marksheet_signatures` (
  `id` int NOT NULL AUTO_INCREMENT,
  `role` enum('principal','hod','class_teacher') COLLATE utf8mb4_unicode_ci NOT NULL,
  `department_id` int DEFAULT NULL,
  `semester` int DEFAULT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `designation` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sign_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `teacher_id` int DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ms_signature` (`role`,`department_id`,`semester`),
  KEY `fk_ms_sig_dept` (`department_id`),
  KEY `fk_ms_sig_teacher` (`teacher_id`),
  KEY `ix_marksheet_signatures_college_id` (`college_id`),
  CONSTRAINT `fk_marksheet_signatures_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `fk_ms_sig_dept` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ms_sig_teacher` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `notice_reads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `notice_id` int NOT NULL,
  `user_id` int NOT NULL,
  `read_at` datetime NOT NULL,
  `dismissed_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_notice_read_notice_user` (`notice_id`,`user_id`),
  KEY `user_id` (`user_id`),
  KEY `ix_notice_reads_college_id` (`college_id`),
  KEY `ix_notice_reads_college_user_dismissed` (`college_id`,`user_id`,`dismissed_at`),
  KEY `ix_notice_reads_college_notice` (`college_id`,`notice_id`),
  CONSTRAINT `fk_notice_reads_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `notice_reads_ibfk_1` FOREIGN KEY (`notice_id`) REFERENCES `notices` (`id`),
  CONSTRAINT `notice_reads_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `notices` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `category` enum('general','exam','holiday','event','fee','urgent') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_role` enum('all','student','teacher') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_pinned` tinyint(1) DEFAULT NULL,
  `author_id` int NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `expires_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `author_id` (`author_id`),
  KEY `ix_notices_college_id` (`college_id`),
  KEY `ix_notices_college_role_pinned_created` (`college_id`,`target_role`,`is_pinned`,`created_at`),
  KEY `ix_notices_college_expires_at` (`college_id`,`expires_at`),
  CONSTRAINT `fk_notices_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `notices_ibfk_1` FOREIGN KEY (`author_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `parent_students` (
  `id` int NOT NULL AUTO_INCREMENT,
  `parent_id` int NOT NULL,
  `student_id` int NOT NULL,
  `relationship` enum('father','mother','guardian','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_parent_student` (`parent_id`,`student_id`),
  KEY `student_id` (`student_id`),
  KEY `ix_parent_students_college_id` (`college_id`),
  KEY `ix_parent_students_college_parent` (`college_id`,`parent_id`),
  KEY `ix_parent_students_college_student` (`college_id`,`student_id`),
  CONSTRAINT `fk_parent_students_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `parent_students_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `parent_students_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `platform_audit_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `actor_user_id` int DEFAULT NULL,
  `college_id` int DEFAULT NULL,
  `action_key` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_type` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_id` int DEFAULT NULL,
  `summary` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `detail_json` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_platform_audit_logs_actor_user_id` (`actor_user_id`),
  KEY `ix_platform_audit_logs_college_id` (`college_id`),
  KEY `ix_platform_audit_logs_created_at` (`created_at`),
  KEY `ix_platform_audit_logs_college_created` (`college_id`,`created_at`),
  KEY `ix_platform_audit_logs_action_created` (`action_key`,`created_at`),
  CONSTRAINT `platform_audit_logs_ibfk_1` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `platform_audit_logs_ibfk_2` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `platform_audit_reads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `audit_log_id` int NOT NULL,
  `user_id` int NOT NULL,
  `read_at` datetime NOT NULL,
  `dismissed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_platform_audit_read_log_user` (`audit_log_id`,`user_id`),
  KEY `ix_platform_audit_reads_user_dismissed` (`user_id`,`dismissed_at`),
  KEY `ix_platform_audit_reads_user_log` (`user_id`,`audit_log_id`),
  KEY `ix_platform_audit_reads_user_id` (`user_id`),
  CONSTRAINT `platform_audit_reads_ibfk_1` FOREIGN KEY (`audit_log_id`) REFERENCES `platform_audit_logs` (`id`),
  CONSTRAINT `platform_audit_reads_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `report_schedule_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_id` int NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '0',
  `send_day` int NOT NULL DEFAULT '0',
  `send_hour` int NOT NULL DEFAULT '7',
  `send_minute` int NOT NULL DEFAULT '0',
  `filter_department_ids` json DEFAULT NULL,
  `filter_semesters` json DEFAULT NULL,
  `filter_admission_years` json DEFAULT NULL,
  `last_sent_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `updated_by` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_report_schedule_college` (`college_id`),
  KEY `updated_by` (`updated_by`),
  KEY `ix_report_schedule_configs_college` (`college_id`),
  CONSTRAINT `report_schedule_configs_ibfk_1` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`) ON DELETE CASCADE,
  CONSTRAINT `report_schedule_configs_ibfk_2` FOREIGN KEY (`updated_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `semester_schedules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_id` int NOT NULL,
  `department_id` int DEFAULT NULL,
  `semester` int NOT NULL,
  `academic_year` int NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_semester_schedule` (`college_id`,`department_id`,`semester`,`academic_year`),
  KEY `created_by` (`created_by`),
  KEY `department_id` (`department_id`),
  KEY `ix_semester_schedules_college` (`college_id`,`academic_year`,`semester`),
  CONSTRAINT `semester_schedules_ibfk_1` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `semester_schedules_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`),
  CONSTRAINT `semester_schedules_ibfk_3` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `student_id_cards` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `photo_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `card_number` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('pending','approved','rejected') COLLATE utf8mb4_unicode_ci NOT NULL,
  `rejection_note` text COLLATE utf8mb4_unicode_ci,
  `submitted_at` datetime DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `reviewed_by` int DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `student_id` (`student_id`),
  UNIQUE KEY `uq_student_id_cards_college_card_number` (`college_id`,`card_number`),
  KEY `reviewed_by` (`reviewed_by`),
  KEY `ix_student_id_cards_college_id` (`college_id`),
  KEY `ix_student_id_cards_college_status_submitted` (`college_id`,`status`,`submitted_at`),
  CONSTRAINT `fk_student_id_cards_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `student_id_cards_ibfk_1` FOREIGN KEY (`reviewed_by`) REFERENCES `users` (`id`),
  CONSTRAINT `student_id_cards_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `student_locations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int NOT NULL,
  `latitude` float DEFAULT NULL,
  `longitude` float DEFAULT NULL,
  `accuracy` float DEFAULT NULL,
  `is_sharing` tinyint(1) NOT NULL,
  `updated_at` datetime DEFAULT NULL,
  `last_arrival_date` date DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `student_id` (`student_id`),
  KEY `ix_student_locations_college_id` (`college_id`),
  CONSTRAINT `fk_student_locations_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `student_locations_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `students` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `roll_number` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `department_id` int NOT NULL,
  `semester` int NOT NULL,
  `face_encoding` blob,
  `face_image_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `enrolled_at` datetime DEFAULT NULL,
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dob` date DEFAULT NULL,
  `blood_group` varchar(5) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `address` text COLLATE utf8mb4_unicode_ci,
  `parent_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `parent_phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `admission_year` int DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  UNIQUE KEY `uq_students_college_roll_number` (`college_id`,`roll_number`),
  KEY `department_id` (`department_id`),
  KEY `ix_students_college_id` (`college_id`),
  KEY `ix_students_college_department_semester` (`college_id`,`department_id`,`semester`),
  CONSTRAINT `fk_students_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `students_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `students_ibfk_2` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `sub_admin_permissions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `college_id` int NOT NULL,
  `user_id` int NOT NULL,
  `module` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `can_view` tinyint(1) NOT NULL DEFAULT '0',
  `can_edit` tinyint(1) NOT NULL DEFAULT '0',
  `can_delete` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sub_admin_perm` (`college_id`,`user_id`,`module`),
  KEY `ix_sub_admin_permissions_college_id` (`college_id`),
  KEY `ix_sub_admin_permissions_user_id` (`user_id`),
  CONSTRAINT `sub_admin_permissions_ibfk_1` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `sub_admin_permissions_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `subjects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `department_id` int NOT NULL,
  `teacher_id` int NOT NULL,
  `semester` int NOT NULL,
  `credit_hours` int DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_subjects_college_code` (`college_id`,`code`),
  KEY `department_id` (`department_id`),
  KEY `teacher_id` (`teacher_id`),
  KEY `ix_subjects_college_id` (`college_id`),
  CONSTRAINT `fk_subjects_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `subjects_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `subjects_ibfk_2` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `teacher_contents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `teacher_id` int NOT NULL,
  `subject_id` int DEFAULT NULL,
  `department_id` int NOT NULL,
  `semester` int NOT NULL,
  `content_type` enum('note','assignment','lab','question') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'note',
  `title` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `body` text COLLATE utf8mb4_unicode_ci,
  `file_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `due_date` date DEFAULT NULL,
  `marks` int DEFAULT NULL,
  `is_published` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `teacher_id` (`teacher_id`),
  KEY `subject_id` (`subject_id`),
  KEY `department_id` (`department_id`),
  KEY `ix_teacher_contents_college_id` (`college_id`),
  KEY `ix_teacher_contents_college_scope_publish` (`college_id`,`department_id`,`semester`,`is_published`),
  KEY `ix_teacher_contents_college_teacher_created` (`college_id`,`teacher_id`,`created_at`),
  KEY `ix_teacher_contents_college_type_publish` (`college_id`,`content_type`,`is_published`),
  CONSTRAINT `fk_teacher_contents_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `teacher_contents_ibfk_1` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`) ON DELETE CASCADE,
  CONSTRAINT `teacher_contents_ibfk_2` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`) ON DELETE SET NULL,
  CONSTRAINT `teacher_contents_ibfk_3` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `teacher_statuses` (
  `id` int NOT NULL AUTO_INCREMENT,
  `teacher_id` int NOT NULL,
  `status` enum('on_campus','in_class','unavailable','off_campus') COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `teacher_id` (`teacher_id`),
  KEY `ix_teacher_statuses_college_id` (`college_id`),
  KEY `ix_teacher_statuses_college_status` (`college_id`,`status`),
  CONSTRAINT `fk_teacher_statuses_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `teacher_statuses_ibfk_1` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `teachers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `employee_id` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `department_id` int NOT NULL,
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `qualification` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `designation` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `joining_date` date DEFAULT NULL,
  `sign_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  UNIQUE KEY `uq_teachers_college_employee_id` (`college_id`,`employee_id`),
  KEY `department_id` (`department_id`),
  KEY `ix_teachers_college_id` (`college_id`),
  KEY `ix_teachers_college_department` (`college_id`,`department_id`),
  CONSTRAINT `fk_teachers_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `teachers_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `teachers_ibfk_2` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `timetable_slots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `department_id` int NOT NULL,
  `semester` int NOT NULL,
  `day_of_week` int NOT NULL,
  `period_no` int NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `subject_id` int DEFAULT NULL,
  `room` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `slot_type` enum('lecture','lab','break','free') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `teacher_id` int DEFAULT NULL,
  `college_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_slot` (`department_id`,`semester`,`day_of_week`,`period_no`),
  KEY `subject_id` (`subject_id`),
  KEY `teacher_id` (`teacher_id`),
  KEY `ix_timetable_slots_college_id` (`college_id`),
  KEY `ix_timetable_slots_college_scope_day` (`college_id`,`department_id`,`semester`,`day_of_week`),
  KEY `ix_timetable_slots_college_teacher_day` (`college_id`,`teacher_id`,`day_of_week`),
  CONSTRAINT `fk_timetable_slots_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`),
  CONSTRAINT `timetable_slots_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `timetable_slots_ibfk_2` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`),
  CONSTRAINT `timetable_slots_ibfk_3` FOREIGN KEY (`teacher_id`) REFERENCES `teachers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('super_admin','admin','sub_admin','teacher','student','parent') COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `sidebar_pins` text COLLATE utf8mb4_unicode_ci,
  `dashboard_widgets` text COLLATE utf8mb4_unicode_ci,
  `college_id` int NOT NULL,
  `must_change_password` tinyint(1) NOT NULL DEFAULT '0',
  `password_changed_at` datetime DEFAULT NULL,
  `password_setup_email_sent_at` datetime DEFAULT NULL,
  `last_login_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_college_email` (`college_id`,`email`),
  KEY `ix_users_college_id` (`college_id`),
  CONSTRAINT `fk_users_college_id` FOREIGN KEY (`college_id`) REFERENCES `colleges` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
