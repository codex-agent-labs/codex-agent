#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

typedef void (^CDXObjectiveCConsumerCompletion)(NSString * _Nullable failureMessage);

FOUNDATION_EXPORT void CDXRunObjectiveCConsumer(CDXObjectiveCConsumerCompletion completion);

NS_ASSUME_NONNULL_END
